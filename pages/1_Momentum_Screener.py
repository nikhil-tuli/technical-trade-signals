"""
Momentum Screener — second sidebar page (file-based, matching
0_Signal_Screener.py's pattern for the same reason: mixing file-based
and callable-based st.Page entries was the earlier state-loss bug).

Reuses, does not duplicate:
  - data_fetch.fetch_universe() — same throttled fetch used by the
    Signal Screener, for whichever universe (Nifty 100 / 500 / Custom)
    is selected. No new fetch function needed.
  - Stock Universe + Custom-ticker handling mirrors
    0_Signal_Screener.py's pattern exactly (same parsing, same
    MAX_CUSTOM_TICKERS cap, same "custom bypasses the shared cache and
    always fetches fresh" rule) — see that file for the original.
  - st.cache_resource pattern for the shared cache — separate cache
    object from Signal Screener's, keyed per-universe (Nifty 100 vs
    500) so switching universes never collides with or evicts a
    different universe's cached fetch.
  - charting.build_plain_chart() for the drill-down view.
  - config.NIFTY_100_MAP / NIFTY_500_MAP for symbol -> company name
    (nse_master_data.py supplies sector + listing date only, and only
    for Nifty 500 members — Custom tickers outside that universe get
    None for sector/listing date; sector and listing-period filters are
    skipped automatically for Custom since that metadata isn't
    available to filter on — see the Custom-tickers handling below).

No "Sort by" selectbox — st.dataframe already supports click-to-sort on
any column header natively (client-side, no recompute), so a duplicate
app-level sort control would just be redundant UI. Table renders with a
sensible initial order (12mo return, descending) and the user re-sorts
by clicking headers.
"""
import datetime as dt
import sys
from pathlib import Path

# See pages/0_Signal_Screener.py's identical comment — same fix, same reason.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd

from config import (
    NIFTY_100_MAP,
    NIFTY_500_MAP,
    MAX_CUSTOM_TICKERS,
    MOMENTUM_RETURN_WINDOWS,
    MOMENTUM_DMA_OPTIONS,
    MOMENTUM_DMA_DEFAULT,
    MOMENTUM_LIQUIDITY_FLOOR_CR_DEFAULT,
    MOMENTUM_LIQUIDITY_LOOKBACK_DAYS,
    MOMENTUM_VOLUME_BASELINE_DAYS_DEFAULT,
    MOMENTUM_VOLUME_RECENT_DAYS,
    MOMENTUM_MIN_LISTING_MONTHS_DEFAULT,
    MOMENTUM_LOOKBACK_MONTHS,
    MOMENTUM_FETCH_PERIOD,
    MOMENTUM_CACHE_TTL_SECONDS,
    MOMENTUM_MASTER_DATA_ASOF,
    MOMENTUM_RISK_FREE_RATE_PCT,
    MOMENTUM_RISK_FREE_RATE_ASOF,
)
from data_fetch import fetch_universe
from momentum_engine import build_momentum_table, apply_filters, sort_table, price_points
from charting import build_plain_chart
import nse_master_data
import how_it_works

# Shared between the Min Sharpe ratio filter's tooltip and the Sharpe
# ratio column's tooltip — one string, so the two can't drift out of
# sync with each other.
SHARPE_DEFINITION = (
    f"Sharpe ratio = (12mo return % − risk-free rate) ÷ annualized volatility. "
    f"Risk-free rate assumed: {MOMENTUM_RISK_FREE_RATE_PCT:g}% (≈India's 91-day T-bill, "
    f"as of {MOMENTUM_RISK_FREE_RATE_ASOF})."
)


@st.cache_resource
def _get_momentum_cache() -> dict:
    """Own st.cache_resource object, deliberately separate from Signal
    Screener's _get_shared_cache() — different universes, different TTL
    semantics, must not share a cache key/dict."""
    return {}


_MOMENTUM_CACHE = _get_momentum_cache()


def _parse_custom_tickers(raw: str) -> list[str]:
    """Identical logic to 0_Signal_Screener.py's helper of the same
    name — kept as a local copy rather than a shared import since it's
    four lines and importing across page files for something this small
    would be more coupling than it's worth."""
    if not raw or not raw.strip():
        return []
    seen = []
    for part in raw.split(","):
        sym = part.strip().upper()
        if sym and sym not in seen:
            seen.append(sym)
    return seen


def _render_screener_tab():
    st.title("Momentum Screener")
    st.caption("Rank stocks by momentum. Sort, filter, drill into any name. Informational only — not a recommendation.")

    with st.container(border=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            _uni_options = ["Nifty 500", "Nifty 100", "Custom"]
            universe_mode = st.selectbox("Stock Universe", _uni_options, key="mom_universe")
        with c2:
            sector_options = ["All sectors"] + nse_master_data.sector_list()
            sector = st.selectbox(
                "Sector", sector_options, key="mom_sector",
                disabled=(universe_mode == "Custom"),
                help="Not available for Custom — sector data only covers the Nifty 500 universe." if universe_mode == "Custom" else None,
            )
        with c3:
            min_listing_months = st.number_input(
                "Min listing period (months)", min_value=0, value=MOMENTUM_MIN_LISTING_MONTHS_DEFAULT,
                step=1, key="mom_min_listing",
                disabled=(universe_mode == "Custom"),
                help=(
                    "Not available for Custom — listing-date data only covers the Nifty 500 universe."
                    if universe_mode == "Custom" else
                    f"Based on NSE listing-date data manually fetched on {MOMENTUM_MASTER_DATA_ASOF} — not "
                    f"live. A stock's actual listing date may have changed since."
                ),
            )
        with c4:
            dma_period = st.selectbox(
                "Price Trend - Last closed price > N-day moving average", MOMENTUM_DMA_OPTIONS,
                index=MOMENTUM_DMA_OPTIONS.index(MOMENTUM_DMA_DEFAULT), key="mom_dma",
            )

        if universe_mode == "Custom":
            custom_tickers_raw = st.text_input(
                "Custom tickers (comma-separated NSE symbols)",
                value=st.session_state.get("mom_stored_custom_tickers", ""),
                placeholder="e.g. TCS, WIPRO, INFY",
                help=f"Replaces the selected universe for this run only — not saved between sessions, "
                     f"max {MAX_CUSTOM_TICKERS} tickers. Sector and listing-period filters are unavailable "
                     f"for Custom since that metadata only covers the Nifty 500 universe.",
                key="mom_custom_tickers_input",
            )
            st.session_state["mom_stored_custom_tickers"] = custom_tickers_raw
        else:
            custom_tickers_raw = ""

        c5, c6 = st.columns(2)
        with c5:
            liquidity_floor = st.number_input(
                "Min annual traded turnover ₹cr",
                min_value=0.0, value=MOMENTUM_LIQUIDITY_FLOOR_CR_DEFAULT, step=50.0, key="mom_liquidity",
                help=f"Actual trailing {MOMENTUM_LIQUIDITY_LOOKBACK_DAYS}-trading-day SUM of daily traded "
                     f"value (Close x Volume), in ₹ crore — a real year of turnover, not a projection from "
                     f"a shorter window.",
            )
        with c6:
            min_price_input = st.number_input(
                "Min last closed price ₹ (blank = no filter, all shown)", min_value=0.0, value=None,
                step=10.0, key="mom_min_price",
            )

        # "Max volatility %" filter DISABLED — see momentum_engine.py's
        # commented-out volatility_pct(). Column removed too, further down.
        # c7 = st.number_input("Max volatility % (12mo, 0 = no filter, all shown)", ...)
        min_sharpe_input = st.number_input(
            "Min Sharpe ratio (blank = no filter, all shown)", min_value=-10.0, value=None,
            step=0.1, key="mom_min_sharpe",
            help=f"Excludes stocks below this Sharpe ratio. {SHARPE_DEFINITION}",
        )

        volume_baseline_days = st.selectbox(
            "Relative Volume baseline (days)",
            [30, 50, 90],
            index=[30, 50, 90].index(MOMENTUM_VOLUME_BASELINE_DAYS_DEFAULT), key="mom_vol_baseline",
            help=(
                f"Sets the denominator (N-day average volume) for the 'Relative Volume %' column. The "
                f"numerator is fixed at a {MOMENTUM_VOLUME_RECENT_DAYS}-day AVERAGE volume (not a single "
                f"day)."
            ),
        )

        exclude_last_month = st.checkbox("Exclude last 1 month from 12mo return", key="mom_exclude_last_month")

        run_clicked = st.button("Generate rankings", type="primary")

    if run_clicked:
        custom_tickers = _parse_custom_tickers(custom_tickers_raw)
        if len(custom_tickers) > MAX_CUSTOM_TICKERS:
            st.error(
                f"Too many custom tickers ({len(custom_tickers)}) — max {MAX_CUSTOM_TICKERS} allowed. "
                f"Shorten the list and click Generate rankings again."
            )
            return

        # Custom tickers are ad hoc/per-request — bypass the shared
        # cache entirely and always fetch fresh (same rule as the
        # Signal Screener). Nifty 100 and Nifty 500 each get their own
        # cache key so switching between them never evicts the other.
        if custom_tickers:
            cache_key = None
            symbols = custom_tickers
        elif universe_mode == "Nifty 100":
            cache_key = "nifty100_momentum"
            symbols = list(NIFTY_100_MAP.keys())
        else:
            cache_key = "nifty500_momentum"
            symbols = list(NIFTY_500_MAP.keys())

        now = dt.datetime.now()
        cache_entry = _MOMENTUM_CACHE.get(cache_key) if cache_key else None
        is_stale = (
            cache_key is None  # custom -> always "stale", i.e. always fetch
            or cache_entry is None
            or (now - cache_entry["fetched_at"]).total_seconds() > MOMENTUM_CACHE_TTL_SECONDS
        )
        if is_stale:
            progress = st.progress(0.0, text=f"Fetching {len(symbols)} symbol(s)…")

            def _progress_cb(done, total, sym):
                progress.progress(done / total, text=f"Fetching {sym} ({done}/{total})")

            price_data, failures = fetch_universe(symbols, period=MOMENTUM_FETCH_PERIOD, progress_callback=_progress_cb)
            progress.empty()
            cache_entry = {"price_data": price_data, "failures": failures, "fetched_at": now}
            if cache_key:
                _MOMENTUM_CACHE[cache_key] = cache_entry

        universe_label = (
            f"Custom · {len(custom_tickers)} stock{'s' if len(custom_tickers) != 1 else ''}"
            if custom_tickers else universe_mode
        )
        st.session_state["mom_has_run"] = True
        st.session_state["mom_run_inputs"] = dict(
            universe_mode=universe_mode, custom_tickers=tuple(custom_tickers),
            cache_key=cache_key, cache_entry=cache_entry, universe_label=universe_label,
        )

    if not st.session_state.get("mom_has_run"):
        st.info("Set your filters and click **Generate rankings** to run the screen.")
        return

    run_inputs = st.session_state["mom_run_inputs"]
    is_custom = bool(run_inputs["custom_tickers"])
    cache_entry = run_inputs["cache_entry"]

    price_data, failures = cache_entry["price_data"], cache_entry["failures"]
    fetched_at = cache_entry["fetched_at"]
    st.caption(f"Last updated: {fetched_at.strftime('%d %b %Y, %H:%M IST')} · {run_inputs['universe_label']} · "
               f"{len(price_data)} fetched, {len(failures)} failed")
    if failures:
        with st.expander(f"{len(failures)} symbol(s) failed to fetch"):
            st.dataframe(
                [{"Symbol": sym, "Error": msg} for sym, msg in failures.items()],
                use_container_width=True, hide_index=True,
            )
    if not price_data:
        st.error("All fetches failed — nothing to rank. See failures above.")
        return

    # --- Stabilize the ranked table across reruns ---
    # st.dataframe's row-selection (on_select="rerun") triggers a full
    # script rerun on every select/deselect click. If we rebuilt `ranked`
    # /`display_df` as a brand-new DataFrame object on every one of those
    # reruns (as before), the grid widget saw a "new" dataframe each time
    # while still holding onto session_state selection/row-count from the
    # PREVIOUS object — this is what caused the reported bug (deselecting
    # a row left only that one row visible instead of restoring the full
    # filtered list). Fix: only recompute when the actual FILTER inputs
    # change; reuse the same DataFrame object across pure-selection
    # reruns so the grid has a stable, unchanging data reference to
    # reconcile its selection state against.
    #
    # Sector/listing-period filters are forced to None for Custom —
    # that metadata only exists for Nifty 500 members, so applying it to
    # a hand-picked Custom list would silently drop tickers the user
    # explicitly asked for rather than filter anything meaningful.
    effective_sector = None if is_custom else sector
    effective_min_listing = None if is_custom else min_listing_months
    # min_price_input / min_sharpe_input are now natively None when the
    # widget is left blank (st.number_input(value=None)) — no more "0
    # means disabled" sentinel conversion needed, and 0 is now a settable
    # real threshold like any other value.
    effective_min_price = min_price_input
    effective_min_sharpe = min_sharpe_input

    filter_signature = (
        run_inputs["universe_mode"], run_inputs["custom_tickers"],
        effective_sector, effective_min_listing, dma_period, liquidity_floor,
        effective_min_price, effective_min_sharpe,
        volume_baseline_days, exclude_last_month, fetched_at,
    )
    if st.session_state.get("mom_filter_sig") != filter_signature:
        table = build_momentum_table(
            price_data, dma_period=dma_period, exclude_last_month=exclude_last_month,
            volume_baseline_days=volume_baseline_days,
        )
        filtered = apply_filters(
            table, sector=effective_sector, min_listing_months=effective_min_listing,
            liquidity_floor_cr=liquidity_floor, min_price=effective_min_price,
            min_sharpe_ratio=effective_min_sharpe,
            require_above_dma=True,
        )
        ranked = sort_table(filtered, sort_by="return_12mo_pct")
        st.session_state["mom_filter_sig"] = filter_signature
        st.session_state["mom_ranked"] = ranked
        # Filters changed -> any previously selected row index may now
        # point at a different stock (or no longer exist) in the new
        # table. Clear the widget's stored selection rather than let a
        # stale index silently carry over.
        st.session_state.pop("mom_table", None)
    else:
        ranked = st.session_state["mom_ranked"]

    if ranked.empty:
        st.warning("No stocks matched these filters. Try loosening the liquidity floor or trend filter.")
        return

    vol_pct_label = "Relative Volume %"
    turnover_label = "Annual traded turnover ₹cr"
    dma_label = f"{dma_period}-day DMA ₹"
    return_pct_labels = {w: f"{w}d returns %" for w in MOMENTUM_RETURN_WINDOWS}

    display_cols = [
        "symbol", "sector", "current_price", "week_52_high", "dma_value",
        "return_12mo_abs", "return_12mo_pct",
        "sector_avg_return_12mo_pct", "relative_to_sector_return_12mo_pct",
    ] + [f"return_{w}d_pct" for w in MOMENTUM_RETURN_WINDOWS] + [
        "sharpe_ratio", "hit_rate_pct",
        "volume_participation_pct", "annual_traded_turnover_cr", "listing_date",
    ]
    column_rename = {
        "symbol": "Stock", "sector": "Sector",
        "current_price": "Last closed price ₹", "week_52_high": "52-week high ₹", "dma_value": dma_label,
        "sector_avg_return_12mo_pct": "Sector avg 12mo returns %",
        "relative_to_sector_return_12mo_pct": "Vs sector 12mo returns (pts)",
        **{f"return_{w}d_pct": lbl for w, lbl in return_pct_labels.items()},
        "return_12mo_abs": "12mo returns ₹", "return_12mo_pct": "12mo returns %",
        "sharpe_ratio": "Sharpe ratio", "hit_rate_pct": "Hit rate %",
        "volume_participation_pct": vol_pct_label, "annual_traded_turnover_cr": turnover_label,
        "listing_date": "Listing date",
    }
    display_df = ranked[display_cols].copy()
    display_df["listing_date"] = display_df["listing_date"].apply(
        lambda d: d.strftime("%Y-%m-%d") if pd.notna(d) else None
    )
    display_df = display_df.rename(columns=column_rename)

    exclude_note = " (excluding the most recent month)" if exclude_last_month else ""
    column_config = {
        "52-week high ₹": st.column_config.NumberColumn(
            help="Highest daily High price over the trailing 252 trading days (~52 weeks). For a stock "
                 "listed less than 252 trading days ago, this uses whatever history is available — "
                 "effectively an all-time high in that case, not a true 52-week figure.",
        ),
        dma_label: st.column_config.NumberColumn(
            help=f"The {dma_period}-day simple moving average of Close price — the same period selected "
                 f"in the 'Price Trend' control above. Every row in this table already has last closed "
                 f"price above this value, since the trend filter is applied before ranking.",
        ),
        "12mo returns ₹": st.column_config.NumberColumn(
            help=f"Close price today minus Close price ~{MOMENTUM_LOOKBACK_MONTHS} months ago{exclude_note}.",
        ),
        "12mo returns %": st.column_config.NumberColumn(
            help=f"% change in Close price over the trailing {MOMENTUM_LOOKBACK_MONTHS} months{exclude_note}.",
        ),
        "Sector avg 12mo returns %": st.column_config.NumberColumn(
            help="The average 12mo returns % across every stock in this stock's sector, computed from the "
                 "full fetched universe BEFORE any filters (sector, liquidity, trend, etc.) were applied — "
                 "so it's the sector's true average, not just the average among the rows currently visible. "
                 "Blank for Custom tickers with no known sector.",
        ),
        "Vs sector 12mo returns (pts)": st.column_config.NumberColumn(
            help="This stock's 12mo returns % minus its sector's average 12mo returns % (percentage-point "
                 "difference, not a ratio). Positive = outperforming its own sector; negative = lagging it. "
                 "This is relative momentum — whether the stock is leading or lagging its peers, not just "
                 "whether it's up in absolute terms.",
        ),
        "Sharpe ratio": st.column_config.NumberColumn(help=SHARPE_DEFINITION),
        "Hit rate %": st.column_config.NumberColumn(
            help=f"% of trading days in the trailing {MOMENTUM_LOOKBACK_MONTHS}-month window{exclude_note} "
                 f"that closed higher than the day before.",
        ),
        vol_pct_label: st.column_config.NumberColumn(
            help=f"({MOMENTUM_VOLUME_RECENT_DAYS}-day average volume ÷ {volume_baseline_days}-day average "
                 f"volume) × 100. Above 100% = recent activity above this stock's own norm; below 100% = "
                 f"quieter than usual. Display-only — does not filter the table.",
        ),
        turnover_label: st.column_config.NumberColumn(
            help=f"Actual trailing {MOMENTUM_LIQUIDITY_LOOKBACK_DAYS}-trading-day SUM of daily traded value "
                 f"(Close x Volume), in ₹ crore — a real year of turnover, not a projection from a shorter "
                 f"window.",
        ),
        "Listing date": st.column_config.TextColumn(
            help=f"From NSE data, manually fetched on {MOMENTUM_MASTER_DATA_ASOF} — not live.",
        ),
    }
    for w, lbl in return_pct_labels.items():
        column_config[lbl] = st.column_config.NumberColumn(
            help=f"% change in Close price over the trailing {w} trading days (today's close vs. the "
                 f"close {w} trading days ago).",
        )

    event = st.dataframe(
        display_df, use_container_width=True, hide_index=True,
        on_select="rerun", selection_mode="single-row", key="mom_table",
        column_config=column_config,
    )

    selected_rows = event.selection.rows if event and event.selection else []
    if selected_rows:
        selected_symbol = ranked.iloc[selected_rows[0]]["symbol"]
        with st.container(border=True):
            st.markdown(f"**{selected_symbol} · drill-down**")
            df_selected = price_data.get(selected_symbol)
            if df_selected is not None:
                fig = build_plain_chart(df_selected, selected_symbol, ma_period=dma_period)
                st.plotly_chart(fig, use_container_width=True)

                # Real close prices + dates behind the returns columns
                # above, for this specific stock — lets you verify the
                # % figures against actual numbers rather than take the
                # calculation on faith.
                points = price_points(df_selected, exclude_last_month=exclude_last_month)
                period_labels = {
                    "today": "Today's close", 30: "30d ago", 60: "60d ago",
                    90: "90d ago", 180: "180d ago", "12mo": f"~252 days / {MOMENTUM_LOOKBACK_MONTHS}mo ago",
                }
                rows = []
                for key, label in period_labels.items():
                    price, date = points.get(key, (None, None))
                    rows.append({
                        "Period": label,
                        "Close ₹": price if price is not None else "—",
                        "Date": date.strftime("%d-%b-%Y") if date is not None else "—",
                    })
                st.caption("Price points behind the return figures above" +
                           (" (12mo row reflects 'exclude last month')" if exclude_last_month else ""))
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


_tab_screener, _tab_how = st.tabs(["Screener", "How this works"])
with _tab_screener:
    _render_screener_tab()
with _tab_how:
    how_it_works.render_momentum_explainer()
