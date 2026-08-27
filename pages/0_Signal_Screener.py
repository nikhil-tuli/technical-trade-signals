"""
Signal Screener — main screening page (file-based, for Streamlit
multi-page navigation via st.navigation/st.Page in app.py).

Made file-based (not a callable passed to st.Page) to match how
"How This Works" is structured — mixing a callable-based page with a
file-based page was the suspected cause of filter/result state not
persisting when switching between sidebar pages. app.py handles
st.set_page_config() and st.navigation() only; this file is pure page
content, executed by Streamlit when this page is selected.
"""
import datetime as dt
import pandas as pd
import streamlit as st

from config import NIFTY_100_MAP, NIFTY_500_MAP, TRADE_TYPE_PARAMS, DEFAULT_TRADE_TYPE, VOLUME_MA_PERIOD_DEFAULT, MIN_RR_DEFAULT, SR_MAX_DISTANCE_PCT_DEFAULT, MAX_CUSTOM_TICKERS
from data_fetch import fetch_universe
from signal_engine import run_screen

CACHE_TTL_SECONDS = 30 * 60  # 30 min, within the 15-60 min range from Section 8.2


@st.cache_resource
def _get_shared_cache() -> dict:
    """
    Returns the SAME dict object across every rerun and every user session.
    This is the correct Streamlit primitive for "shared, survives reruns"
    state (Section 8.2) — a plain module-level dict does NOT work for this:
    Streamlit re-executes the whole script top-to-bottom on every widget
    interaction, so a plain top-level dict gets recreated (and wiped) on
    every single rerun, not just on a real app restart. st.cache_resource
    is what actually persists a shared mutable object across that.
    """
    return {}


_SHARED_CACHE = _get_shared_cache()

def _render_page():
    # Sticky header was tried (position: sticky, then position: fixed) and
    # reverted: a fixed-position header spanning the full viewport width
    # (left:0; right:0) draws directly over Streamlit's sidebar too, not
    # just the main content area — this broke the multi-page nav ("How
    # This Works") once it was added, squashing it instead of showing a
    # proper full-height sidebar. Streamlit's sidebar width is also
    # user-resizable, so there's no reliable fixed CSS offset that avoids
    # it. A working sidebar matters more than a sticky header, so this
    # reverts to a plain, non-sticky title/caption per the original
    # "can revert if failing" agreement.
    st.title("Signal Screener")
    st.caption("Candlestick pattern + volume + Support/Resistance + Reward:Risk — all four confirmed before a signal shows.")

    # Note: "How this works" page (pattern definitions, R:R/S/R methodology,
    # confluence explanation) is planned as a separate page post-cleanup —
    # not built yet. Content that used to live in two info expanders here
    # was removed rather than left in place, since it's being redesigned
    # for that page rather than reused as-is.

    # --- Input panel ---
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            # IMPORTANT: persistence here is deliberately decoupled from
            # the widget's own `key=`. A debug test confirmed plain
            # session_state entries (not tied to any widget) survive
            # switching sidebar pages correctly, but widget-linked state
            # did NOT reliably survive the same switch even with key= and
            # an explicit index=/value= default — Streamlit appears to
            # treat widget-scoped state differently from a plain dict
            # entry across page navigation. Fix: store the value under our
            # OWN separate key ("stored_trade_type", not "trade_type_select")
            # right after the widget renders, and always initialize the
            # widget FROM that separate key — mirroring the exact pattern
            # proven to work.
            _tt_options = ["Short-term", "Long-term"]
            _tt_default = st.session_state.get("stored_trade_type", _tt_options[0])
            trade_type_label = st.selectbox(
                "Trade Type", _tt_options,
                index=_tt_options.index(_tt_default),
                key="trade_type_select"
            )
            st.session_state["stored_trade_type"] = trade_type_label
            trade_type = "short_term" if trade_type_label == "Short-term" else "long_term"
        with c2:
            _uni_options = ["Nifty 100", "Nifty 500", "Custom"]
            _uni_default = st.session_state.get("stored_universe_mode", _uni_options[0])
            universe_mode = st.selectbox(
                "Stock Universe", _uni_options,
                index=_uni_options.index(_uni_default),
                key="universe_mode_select"
            )
            st.session_state["stored_universe_mode"] = universe_mode
        with c3:
            if universe_mode == "Custom":
                custom_tickers_raw = st.text_input(
                    "Custom tickers (comma-separated NSE symbols)",
                    value=st.session_state.get("stored_custom_tickers", ""),
                    placeholder="e.g. TCS, WIPRO, INFY",
                    help=f"Replaces the selected universe for this run only — not saved between sessions, "
                         f"max {MAX_CUSTOM_TICKERS} tickers.",
                    key="custom_tickers_input"
                )
                st.session_state["stored_custom_tickers"] = custom_tickers_raw
            else:
                custom_tickers_raw = ""

        st.caption(
            "Short-term uses tighter, more recent price data; Long-term looks further back for more "
            "established levels. Switching modes adjusts several settings together automatically.",
            help=(
                f"{trade_type_label} · "
                f"S/R lookback: {TRADE_TYPE_PARAMS[trade_type]['sr_lookback_months']} months · "
                f"Fractal width: {TRADE_TYPE_PARAMS[trade_type]['fractal_width']} candles · "
                f"Touch-spacing: {TRADE_TYPE_PARAMS[trade_type]['min_touch_separation_days']} days · "
                f"Primary Trend MA: {TRADE_TYPE_PARAMS[trade_type]['primary_trend_ma']} · "
                f"Pattern prior-trend lookback: {TRADE_TYPE_PARAMS[trade_type]['pattern_prior_trend_lookback']} candles"
            )
        )

        # Expander's title renders BEFORE its contents, so it can't read
        # the widgets' return values directly (chicken-and-egg). Reading
        # from our own "stored_*" keys here (same reasoning as above).
        _vma_display = st.session_state.get("stored_volume_ma_period", VOLUME_MA_PERIOD_DEFAULT)
        _minrr_display = st.session_state.get("stored_min_rr", MIN_RR_DEFAULT)
        _maxsr_display = st.session_state.get("stored_max_sr_distance", SR_MAX_DISTANCE_PCT_DEFAULT)

        # `key=` here is essential, not cosmetic: without it, Streamlit
        # identifies an expander by its label text. Since the label above
        # changes as you edit the values inside it, Streamlit would treat
        # every edit as a brand-new expander element and reset it to
        # collapsed — this key keeps its identity (and open/closed state)
        # stable across reruns regardless of what the label says.
        with st.expander(
            f"Advanced settings — Volume MA {_vma_display}d, "
            f"Min R:R {_minrr_display}x, Max SL distance {_maxsr_display}%",
            key="advanced_settings_expander",
        ):
            a1, a2, a3 = st.columns(3)
            with a1:
                volume_ma_period = st.number_input(
                    "Volume MA period (days)",
                    value=st.session_state.get("stored_volume_ma_period", VOLUME_MA_PERIOD_DEFAULT),
                    min_value=2, max_value=60,
                    key="volume_ma_period_input"
                )
                st.session_state["stored_volume_ma_period"] = volume_ma_period
            with a2:
                min_rr = st.number_input(
                    "Min Reward:Risk",
                    value=st.session_state.get("stored_min_rr", MIN_RR_DEFAULT),
                    min_value=0.5, step=0.1,
                    key="min_rr_input"
                )
                st.session_state["stored_min_rr"] = min_rr
            with a3:
                max_sr_distance_pct = st.number_input(
                    "Max SL distance from S/R (%)",
                    value=st.session_state.get("stored_max_sr_distance", SR_MAX_DISTANCE_PCT_DEFAULT),
                    min_value=0.5, step=0.5,
                    help="The candle-based stop-loss must sit within this % of the nearest qualifying S/R zone, or the setup is excluded.",
                    key="max_sr_distance_input"
                )
                st.session_state["stored_max_sr_distance"] = max_sr_distance_pct

        run_clicked = st.button("Generate Signals", type="primary")

    def _parse_custom_tickers(raw: str) -> list[str]:
        if not raw or not raw.strip():
            return []
        seen = []
        for part in raw.split(","):
            sym = part.strip().upper()
            if sym and sym not in seen:
                seen.append(sym)
        return seen

    # Streamlit reruns this whole script on EVERY widget interaction, not
    # just the button click — selecting a different stock in the Details
    # dropdown below, or typing in Search, also triggers a full rerun.
    # Without storing results in st.session_state, those unrelated
    # interactions would fall through to "click Generate Signals" below
    # and wipe out everything that was just computed.
    if run_clicked:
        custom_tickers = _parse_custom_tickers(custom_tickers_raw)
        if len(custom_tickers) > MAX_CUSTOM_TICKERS:
            st.error(
                f"Too many custom tickers ({len(custom_tickers)}) — max {MAX_CUSTOM_TICKERS} allowed. "
                f"Shorten the list and click Generate Signals again."
            )
            return
        st.session_state["has_run"] = True
        st.session_state["screen_inputs"] = dict(
            trade_type=trade_type, volume_ma_period=volume_ma_period,
            min_rr=min_rr, max_sr_distance_pct=max_sr_distance_pct,
            custom_tickers=tuple(custom_tickers), universe_mode=universe_mode,
        )

    if not st.session_state.get("has_run"):
        st.info("Set your inputs and click **Generate Signals** to run the screen.")
        return

    # Use the inputs captured at the moment of the last actual click — not
    # whatever the widgets currently show — so an in-between filter tweak
    # (e.g. typing in Search) before the next click doesn't silently change
    # what's being screened without the user asking for a re-run.
    saved = st.session_state["screen_inputs"]

    # If any GATING filter (Trade Type, Volume MA, Min R:R, Max SR
    # distance, Custom tickers) has been changed since the last actual
    # click, the results below are stale relative to what's currently
    # shown in the inputs — hide them and prompt a re-run, rather than
    # silently displaying results for settings that no longer match the
    # screen. Search and Pattern Type are deliberately excluded from this
    # check: those filter the already-computed results live and don't
    # require a re-screen.
    current_gating = dict(
        trade_type=trade_type, volume_ma_period=volume_ma_period,
        min_rr=min_rr, max_sr_distance_pct=max_sr_distance_pct,
        custom_tickers=tuple(_parse_custom_tickers(custom_tickers_raw)), universe_mode=universe_mode,
    )
    if current_gating != saved:
        st.warning("Filters changed — click **Generate Signals** to refresh results for the new settings.")
        return

    trade_type = saved["trade_type"]
    volume_ma_period = saved["volume_ma_period"]
    min_rr = saved["min_rr"]
    max_sr_distance_pct = saved["max_sr_distance_pct"]
    custom_tickers = saved["custom_tickers"]
    saved_universe_mode = saved["universe_mode"]

    # --- Fetch (manual TTL cache, shared across users — Section 8.2) ---
    # Custom tickers are ad hoc / per-request (not persisted, not shared
    # across users), so they bypass the shared cache entirely and always
    # fetch fresh. Nifty 100 and Nifty 500 both use the shared cache, but
    # under DIFFERENT cache keys (see below) since they're different
    # universes — one cache key must mean the same thing for everyone.
    if custom_tickers:
        symbols = custom_tickers
        company_map = {t: t for t in custom_tickers}
        universe_label = f"Custom · {len(custom_tickers)} stock{'s' if len(custom_tickers) != 1 else ''}"
    elif saved_universe_mode == "Nifty 500":
        symbols = tuple(NIFTY_500_MAP.keys())
        company_map = NIFTY_500_MAP
        universe_label = "Nifty 500"
    else:
        symbols = tuple(NIFTY_100_MAP.keys())
        company_map = NIFTY_100_MAP
        universe_label = "Nifty 100"

    period = "18mo" if trade_type == "long_term" else "9mo"

    if custom_tickers:
        progress_bar = st.progress(0, text="Starting fetch…")

        def _progress(done, total, sym):
            progress_bar.progress(done / total, text=f"Fetching data — {done} / {total} symbols ({sym})")

        universe_data, fetch_failures = fetch_universe(list(symbols), period=period, progress_callback=_progress)
        fetched_at = dt.datetime.now()
        progress_bar.empty()
    else:
        cache_key = f"universe_data::{universe_label}::{period}"

        cached_entry = _SHARED_CACHE.get(cache_key)
        cache_valid = (
            cached_entry is not None
            and (dt.datetime.now() - cached_entry["fetched_at"]).total_seconds() < CACHE_TTL_SECONDS
        )

        if cache_valid:
            with st.spinner("Loading cached data…"):
                universe_data = dict(cached_entry["data"])
                cached_failures = dict(cached_entry.get("failures", {}))
            fetched_at = cached_entry["fetched_at"]

            # Cache stores successes AND failures together, but a failure
            # (timeout, transient network issue) is not necessarily still
            # failing a minute later — only the successful fetches are
            # genuinely "cacheable" data; a prior failure means we simply
            # don't have that symbol's data yet, and every subsequent
            # click should keep trying for it rather than treating it as
            # a settled, cache-worthy result for the rest of the TTL
            # window.
            if cached_failures:
                retry_symbols = list(cached_failures.keys())
                retry_progress = st.progress(0, text=f"Retrying {len(retry_symbols)} previously failed symbol(s)…")

                def _retry_progress(done, total, sym):
                    retry_progress.progress(done / total, text=f"Retrying {done} / {total} previously failed symbol(s) ({sym})")

                retried_data, retried_failures = fetch_universe(retry_symbols, period=period, progress_callback=_retry_progress)
                retry_progress.empty()
                universe_data.update(retried_data)
                fetch_failures = retried_failures  # only symbols still failing after retry
                # Update the shared cache in place so other users within
                # this TTL window benefit from the retry too, without
                # resetting the TTL clock (fetched_at unchanged) — this
                # isn't a fresh fetch of everything, just a correction of
                # what was previously known to be incomplete.
                _SHARED_CACHE[cache_key] = {
                    "data": universe_data, "fetched_at": fetched_at, "failures": fetch_failures,
                }
            else:
                fetch_failures = {}
        else:
            progress_bar = st.progress(0, text="Starting fetch…")

            def _progress(done, total, sym):
                progress_bar.progress(done / total, text=f"Fetching data — {done} / {total} symbols ({sym})")

            universe_data, fetch_failures = fetch_universe(list(symbols), period=period, progress_callback=_progress)
            fetched_at = dt.datetime.now()
            _SHARED_CACHE[cache_key] = {"data": universe_data, "fetched_at": fetched_at, "failures": fetch_failures}
            progress_bar.empty()

    def _ordinal_date(d: dt.datetime) -> str:
        day = d.day
        suffix = "th" if 11 <= day % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        return f"{day}{suffix} {d.strftime('%b %H:%M')} IST"

    failures = fetch_failures
    if failures:
        with st.expander(f"⚠️ {len(failures)} symbols failed to fetch — click for details"):
            st.dataframe(
                pd.DataFrame([{"Symbol": s, "Error": e} for s, e in failures.items()]),
                use_container_width=True, hide_index=True,
            )
        if len(universe_data) == 0:
            st.error("All symbol fetches failed — check the error details above before trusting a '0 signals' result.")
            return

    # --- Screen ---
    with st.spinner("Evaluating signals…"):
        signals, exclusions = run_screen(universe_data, company_map, trade_type, volume_ma_period, min_rr, max_sr_distance_pct)

    # One compact status line instead of three separate ones (fetch info,
    # screened/signal/excluded counts) — reduces stacked "meta" elements
    # a trader has to read past before reaching the actual signals. Counts
    # here are the hard-gate result (all 4 checks passed) — Pattern/Search
    # below only narrow what's DISPLAYED, they don't change what "matched".
    total_screened = len(universe_data)
    st.caption(
        f"{universe_label} · Updated {_ordinal_date(fetched_at)} · "
        f"{total_screened} screened → **{len(signals)} signal{'s' if len(signals) != 1 else ''}**, "
        f"{len(exclusions)} excluded"
        + (f" · {len(failures)} fetch failures" if failures else "")
    )

    # Breakdown only shown when there's actually something to explain —
    # an empty "See breakdown" box (e.g. 0 excluded) is pure clutter.
    # Note: no longer search-filterable — Search now renders further down
    # (below the Signals heading), so it isn't defined yet at this point
    # in the script. Minor trade-off for the cleaner layout below.
    if exclusions:
        with st.expander("Why were stocks excluded?"):
            rollup = {}
            for exc in exclusions:
                for r in exc.reasons:
                    rollup[r] = rollup.get(r, 0) + 1
            st.caption(" · ".join(f"{k}: **{v}**" for k, v in rollup.items()))
            st.caption("Counts above don't sum to the excluded total — a stock can fail more than one gate.")
            exc_rows = [{"Symbol": e.symbol, "Failed gates": ", ".join(e.reasons)} for e in exclusions]
            exc_rows.sort(key=lambda r: r["Symbol"])
            st.dataframe(pd.DataFrame(exc_rows), use_container_width=True, hide_index=True)

    # --- Output table ---
    st.subheader(f"Signals — {len(signals)} matched")

    if not signals:
        st.warning("No active signals match the current filters.")
        return

    st.caption(
        "Every row already meets all core checks. TA Indicators shows how many of "
        "RSI/MACD/Supertrend/Aroon agree — additional context, not a filter."
    )

    # Pattern/Search live here (not in the input panel above, and not
    # above the heading) because they filter the results already
    # generated — no re-screen needed — and narrow the VIEW below, not
    # the "matched" count above.
    f1, f2 = st.columns(2)
    with f1:
        _pf_options = ["All patterns", "Bullish only", "Bearish only"]
        _pf_default = st.session_state.get("stored_pattern_filter", _pf_options[0])
        pattern_filter = st.selectbox(
            "Pattern types", _pf_options,
            index=_pf_options.index(_pf_default),
            key="pattern_filter_select"
        )
        st.session_state["stored_pattern_filter"] = pattern_filter
    with f2:
        search = st.text_input(
            "Search Symbol / Company",
            value=st.session_state.get("stored_search", ""),
            key="search_input"
        )
        st.session_state["stored_search"] = search

    view_signals = signals
    if pattern_filter == "Bullish only":
        view_signals = [s for s in view_signals if s.direction == "bullish"]
    elif pattern_filter == "Bearish only":
        view_signals = [s for s in view_signals if s.direction == "bearish"]
    if search:
        s_up = search.upper()
        view_signals = [s for s in view_signals if s_up in s.symbol.upper() or s_up in s.company.upper()]

    if not view_signals:
        st.info("No signals match the current Pattern/Search filter.")
        return

    rows = []
    for s in view_signals:
        rows.append({
            "Symbol": f"{s.symbol} — {s.pattern} ({s.formation_date.strftime('%d %b')})",
            "Direction": "Bullish" if s.direction == "bullish" else "Bearish",
            "Trade Levels": f"Entry ₹{s.entry} · SL ₹{s.stop_loss} · Target ₹{s.target} ({s.rr}x)",
            "Primary Trend": s.primary_trend["trend"],
            "TA Indicators": f"{s.confluence['confirming_count']}/4 confirming",
        })
    df_out = pd.DataFrame(rows)
    # Click a row to see its Details below — replaces the earlier separate
    # dropdown, which duplicated info already visible in the table and
    # needed a second interaction. Requires Streamlit's dataframe selection
    # API (on_select/selection_mode), available from Streamlit ~1.35+; if
    # running an older version, this will raise — upgrade Streamlit rather
    # than working around it, since the fallback (a manual selectbox) is
    # exactly what this replaces.
    event = st.dataframe(
        df_out, use_container_width=True, hide_index=True,
        on_select="rerun", selection_mode="single-row",
    )
    selected_rows = event.selection.rows if event and event.selection else []

    if not selected_rows:
        st.caption("Click a row above to see its Details.")
    else:
        sig = view_signals[selected_rows[0]]
        d = sig.details

        st.markdown(f"**{sig.symbol} Trade Levels**")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Entry", f"₹{sig.entry}")
        m2.metric("Stop-loss", f"₹{sig.stop_loss}")
        m3.metric("Target", f"₹{sig.target}")
        m4.metric("Reward:Risk", f"{sig.rr}x")

        st.caption(
            f"Signal formed on **{sig.formation_date.strftime('%d %b %Y')}**, still **Active** — "
            f"price hasn't closed beyond the stop-loss (₹{sig.stop_loss}) or target (₹{sig.target}) since."
        )

        # --- Why this pattern qualified ---
        st.markdown("**Why this pattern qualified**")

        trade_type_label_d = "Short-term" if d.get("trade_type") == "short_term" else "Long-term"
        st.write(
            f"- **Candlestick pattern:** {sig.pattern}, detected on the {sig.formation_date.strftime('%d %b %Y')} "
            f"candle — checked over the last **{d.get('prior_trend_lookback', '—')} candles** "
            f"({trade_type_label_d} mode)"
        )

        ptd = d.get("prior_trend_dates")
        if ptd:
            st.write(
                f"- **Required prior trend:** {d.get('prior_trend_required', '—')} — confirmed from "
                f"**{ptd['start'].strftime('%d %b')} to {ptd['end'].strftime('%d %b %Y')}** "
                f"(**{ptd['days']} trading days**)"
            )
        # else: pattern has no prior-trend requirement (e.g. Marubozu) — nothing shown, per spec

        vol_today = d.get("volume_today")
        vol_ma = d.get("volume_ma")
        vol_ratio = d.get("volume_ratio")
        vol_ma_period = d.get("volume_ma_period")
        st.write(
            f"- **Volume:** signal-day volume was **{vol_today:,.0f}** shares, its "
            f"**{vol_ma:,.0f}**-share **{vol_ma_period}-day** moving average — **{vol_ratio}x** the average"
            if vol_today is not None else "- Volume: data unavailable"
        )

        # --- Support & Resistance ---
        st.markdown("**Support & Resistance**")

        st.write(f"- **Entry:** ₹{sig.entry}, considered on **{sig.formation_date.strftime('%d %b %Y')}**")

        sl_raw = d.get("sl_raw")
        buf = d.get("sl_buffer_pct")
        st.write(
            f"- **Stop-loss calculation:** raw candle "
            f"{'low' if sig.direction == 'bullish' else 'high'} of ₹{sl_raw}, "
            f"{'reduced' if sig.direction == 'bullish' else 'increased'} by a **{buf}%** buffer → "
            f"final stop-loss **₹{sig.stop_loss}**"
        )

        val_lower = d.get("sr_validation_zone_lower")
        val_upper = d.get("sr_validation_zone_upper")
        val_touches = d.get("sr_validation_zone_touches")
        val_dist = d.get("sr_validation_distance_pct")
        val_max_dist = d.get("max_sr_distance_threshold")
        val_last_touch = d.get("sr_validation_last_touch")
        st.write(
            f"- **Nearest {'support' if sig.direction == 'bullish' else 'resistance'} zone used to validate "
            f"the stop-loss:** ₹{val_lower}–₹{val_upper} band (**{val_touches} touches**, most recently on "
            f"**{val_last_touch.strftime('%d %b %Y') if val_last_touch is not None else '—'}**) — "
            f"**{val_dist}%** away from the stop-loss (max allowed: **{val_max_dist}%**)"
        )

        tgt_lower = d.get("sr_target_zone_lower")
        tgt_upper = d.get("sr_target_zone_upper")
        tgt_touches = d.get("sr_target_zone_touches")
        tgt_last_touch = d.get("sr_target_last_touch")
        near_edge_label = "lower" if sig.direction == "bullish" else "upper"
        st.write(
            f"- **Target calculation:** nearest {'resistance' if sig.direction == 'bullish' else 'support'} "
            f"zone ₹{tgt_lower}–₹{tgt_upper} band (**{tgt_touches} touches**, most recently on "
            f"**{tgt_last_touch.strftime('%d %b %Y') if tgt_last_touch is not None else '—'}**) — target set "
            f"at its **near ({near_edge_label}) edge, ₹{sig.target}**"
        )

        # --- Reward:Risk ---
        st.markdown("**Reward:Risk**")
        reward = abs(sig.target - sig.entry)
        risk = abs(sig.entry - sig.stop_loss)
        min_rr_threshold = d.get("min_rr_threshold")
        st.write(
            f"- **R:R = {sig.rr}x** (minimum required: **{min_rr_threshold}x**) — calculated as "
            f"(Target − Entry) / (Entry − Stop-loss) = "
            f"(₹{sig.target} − ₹{sig.entry}) / (₹{sig.entry} − ₹{sig.stop_loss}) = "
            f"₹{reward:.2f} / ₹{risk:.2f} = **{sig.rr}x**"
        )

        # --- Primary Trend ---
        st.markdown("**Primary Trend**")
        pt = sig.primary_trend
        trend_label = pt.get("trend", "—")
        ma_period = pt.get("ma_period", "—")
        ma_value = pt.get("ma_value", "—")
        close_now = pt.get("close_now", "—")
        slope = pt.get("slope", "—")
        ma_then = pt.get("ma_then", "—")
        slope_days = pt.get("slope_lookback_days", "—")
        flip_count = pt.get("flip_count", "—")
        flip_window = pt.get("sideways_flip_window", "—")

        if trend_label == "Up":
            st.write(
                f"- **Up** — price (₹{close_now}) is above the {ma_period}-day moving average (₹{ma_value}), "
                f"and that average has **risen** from ₹{ma_then} over the last {slope_days} days"
            )
        elif trend_label == "Down":
            st.write(
                f"- **Down** — price (₹{close_now}) is below the {ma_period}-day moving average (₹{ma_value}), "
                f"and that average has **fallen** from ₹{ma_then} over the last {slope_days} days"
            )
        elif trend_label == "Sideways":
            st.write(
                f"- **Sideways** — price has crossed back and forth over the {ma_period}-day moving average "
                f"(currently ₹{ma_value}) **{flip_count} times** in the last {flip_window} candles, "
                f"with no clear direction"
            )
        else:
            st.write(f"- **{trend_label}** — not enough price history yet to determine trend")

        st.markdown("**TA Indicators (context, not a filter)**")
        cv = sig.confluence["raw_values"]
        i1, i2, i3, i4 = st.columns(4)
        i1.metric("RSI", cv.get("RSI", "—"))
        i2.metric("MACD", cv.get("MACD", "—"))
        i3.metric("Supertrend", cv.get("Supertrend", "—"))
        i4.metric("Aroon", cv.get("Aroon", "—"))



_render_page()