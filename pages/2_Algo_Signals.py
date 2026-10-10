"""
Algo Signals — high-volume breakout and retest setups.

File-based page (same pattern as the other two). Scanner logic lives in
algo_scanner.py, chart in algo_charting.py (Altair). Universe/custom-ticker
handling mirrors the Momentum Screener: Nifty 500 / Nifty 100 cached per
universe (one fetch per completed market session), Custom always fetches fresh.
Every scan starts from the "Run scan" button.
"""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from config import (
    NIFTY_100_MAP, NIFTY_500_MAP, MAX_CUSTOM_TICKERS, ALGO_FETCH_PERIOD,
    ALGO_VOLUME_LOOKBACK, ALGO_VOLUME_MULTIPLIER, ALGO_MAX_BREAKOUT_AGE,
    ALGO_MIDPOINT_TOLERANCE_PCT,
)
from data_fetch import fetch_universe
import algo_scanner
from algo_charting import build_algo_chart
import how_it_works


@st.cache_resource
def _get_algo_cache() -> dict:
    """Own cache dict, keyed per universe; entries hold price data tagged
    with the market-session date they were fetched for."""
    return {}


_CACHE = _get_algo_cache()


def _parse_custom_tickers(raw: str) -> list[str]:
    seen = []
    for part in (raw or "").split(","):
        sym = part.strip().upper()
        if sym and sym not in seen:
            seen.append(sym)
    return seen


def _fmt_date(iso_or_date) -> str:
    return iso_or_date.strftime("%d-%m-%Y")


def _latest_candle_date(price_data):
    dates = []
    for raw in price_data.values():
        d = algo_scanner.drop_incomplete_last_candle(algo_scanner.normalize_candles(raw))
        if not d.empty:
            dates.append(d.index[-1].date())
    return max(dates) if dates else None


def _run_scan(universe_mode: str, custom_raw: str) -> None:
    custom = _parse_custom_tickers(custom_raw) if universe_mode == "Custom" else []
    if universe_mode == "Custom":
        if not custom:
            st.error("Enter at least one NSE symbol for Custom.")
            return
        if len(custom) > MAX_CUSTOM_TICKERS:
            st.error(f"Too many custom tickers ({len(custom)}) — max {MAX_CUSTOM_TICKERS}.")
            return
        cache_key, symbols, label = None, custom, f"Custom · {len(custom)} stock{'s' if len(custom) != 1 else ''}"
    elif universe_mode == "Nifty 100":
        cache_key, symbols, label = "nifty100_algo", list(NIFTY_100_MAP), "Nifty 100"
    else:
        cache_key, symbols, label = "nifty500_algo", list(NIFTY_500_MAP), "Nifty 500"

    session_key = algo_scanner.data_session_key()
    entry = _CACHE.get(cache_key) if cache_key else None
    bar = st.progress(0.0, text="Loading scanner cache..." if entry else f"Fetching {len(symbols)} symbol(s)…")
    try:
        if entry is None or entry["session"] != session_key:
            def _fetch_cb(done, total, sym):
                bar.progress(done / total * 0.5, text=f"Fetching {sym} ({done} of {total})")
            price_data, failures = fetch_universe(symbols, period=ALGO_FETCH_PERIOD, progress_callback=_fetch_cb)
            entry = {"price_data": price_data, "failures": failures, "session": session_key,
                     "fetched_at": algo_scanner.now_ist()}
            if cache_key:
                _CACHE[cache_key] = entry

        def _scan_cb(done, total, matches):
            bar.progress(0.5 + done / max(total, 1) * 0.5,
                         text=f"Scanning {done} of {total} · {matches} breakout{'s' if matches != 1 else ''} found")
        results, scanned = algo_scanner.scan_universe(entry["price_data"], progress_callback=_scan_cb)
        error = None if entry["price_data"] else "Could not load price data for any symbol. See failures below."
    except Exception as e:  # surfaced clearly, never a silent empty table
        results, scanned, error = [], 0, f"Scan failed: {type(e).__name__}: {e}"
        entry = {"failures": {}, "fetched_at": algo_scanner.now_ist()}
    finally:
        bar.empty()

    st.session_state["algo_has_run"] = True
    st.session_state["algo_state"] = dict(
        results=results, scanned=scanned, error=error, label=label,
        failures=entry.get("failures", {}), fetched_at=entry["fetched_at"],
        data_asof=_latest_candle_date(entry.get("price_data", {})) or algo_scanner.data_session_key(),
    )
    st.session_state["algo_table_df"] = algo_scanner.results_to_table(results)
    st.session_state.pop("algo_table", None)  # selection from a previous run is meaningless now


def _render_scanner():
    st.title("High-volume breakout and retest setups")
    st.caption("Daily candles from Yahoo Finance (adjusted). Informational only — not a recommendation.")

    with st.container(border=True):
        c1, c2 = st.columns([1, 2])
        with c1:
            universe = st.selectbox("Stock Universe", ["Nifty 500", "Nifty 100", "Custom"], key="algo_universe")
        custom_raw = ""
        with c2:
            if universe == "Custom":
                custom_raw = st.text_input(
                    "Custom tickers (comma-separated NSE symbols)", placeholder="e.g. TCS, WIPRO, INFY",
                    key="algo_custom", help=f"Max {MAX_CUSTOM_TICKERS}. Always fetched fresh, not cached.")
        run = st.button("Run scan", type="primary", key="algo_run")

    if run:
        _run_scan(universe, custom_raw)

    if not st.session_state.get("algo_has_run"):
        st.info("Choose a universe and click **Run scan**.")
        return

    s = st.session_state["algo_state"]
    results, df = s["results"], st.session_state["algo_table_df"]

    m1, m2 = st.columns(2)
    m1.metric("Triggered breakouts", len(results))
    m2.metric("Stocks scanned", s["scanned"])
    st.caption(f"{s['label']} · data as of {_fmt_date(s['data_asof'])} · fetched "
               f"{s['fetched_at'].strftime('%d-%m-%Y %H:%M')} IST")

    if s["error"]:
        st.error(s["error"])
    if s["failures"]:
        with st.expander(f"{len(s['failures'])} symbol(s) failed to fetch"):
            st.dataframe([{"Symbol": k, "Error": v} for k, v in s["failures"].items()],
                         use_container_width=True, hide_index=True)
    if s["error"]:
        return

    st.subheader("Triggered Breakouts")
    if df.empty:
        st.info("No breakout retest setups match the current parameters.")
        return

    column_config = {
        "Rank": st.column_config.NumberColumn(
            help="Position after sorting by age (lowest first), then by closeness to the midpoint.", format="%d"),
        "Symbol": st.column_config.TextColumn(help="NSE symbol of the stock."),
        "Current Price": st.column_config.NumberColumn(
            help="Close of the latest completed candle.", format="%.2f"),
        "Breakout Date": st.column_config.DateColumn(
            help="Date of the high-volume breakout candle.", format="DD-MM-YYYY"),
        "Age": st.column_config.NumberColumn(
            help=f"Candles since the breakout candle. A setup expires after {ALGO_MAX_BREAKOUT_AGE}.", format="%d"),
        "Breakout Vol": st.column_config.NumberColumn(
            help=f"Breakout-candle volume divided by the average volume of the {ALGO_VOLUME_LOOKBACK} candles before it.",
            format="%.2fx"),
        "Retest Distance": st.column_config.NumberColumn(
            help=f"Current price versus the breakout candle's midpoint, (high + low) / 2. "
                 f"Must be within {ALGO_MIDPOINT_TOLERANCE_PCT:g}% either way.", format="%+.2f%%"),
        "Peak Gains": st.column_config.NumberColumn(
            help="Gain from the breakout close to the highest high reached since.", format="%+.2f%%"),
        "Retracement": st.column_config.NumberColumn(
            help="Fall from that highest high to the current price.", format="%+.2f%%"),
    }
    event = st.dataframe(df, use_container_width=True, hide_index=True, on_select="rerun",
                         selection_mode="single-row", key="algo_table", column_config=column_config)

    rows = event.selection.rows if event and event.selection else []
    if rows and rows[0] < len(results):
        r = results[rows[0]]
        with st.container(border=True):
            st.markdown(
                f"**{r['symbol']}**" + (f" · {r['company_name']}" if r["company_name"] else "") +
                f" · breakout {_fmt_date(dt.date.fromisoformat(r['breakout_date']))}"
                f" · {r['days_since']} candles ago · midpoint {r['midpoint']:,.2f} · now {r['current_price']:,.2f}")
            st.altair_chart(build_algo_chart(r), use_container_width=True)
            st.caption(f"Amber band: midpoint ±{ALGO_MIDPOINT_TOLERANCE_PCT:g}%. Amber volume bar = breakout candle; "
                       f"dotted amber line = {ALGO_VOLUME_MULTIPLIER:g}x the {ALGO_VOLUME_LOOKBACK}-candle average.")
    else:
        st.caption("Select a row to see its chart.")


_tab_scan, _tab_how = st.tabs(["Scanner", "How this works"])
with _tab_scan:
    _render_scanner()
with _tab_how:
    how_it_works.render_algo_explainer()
