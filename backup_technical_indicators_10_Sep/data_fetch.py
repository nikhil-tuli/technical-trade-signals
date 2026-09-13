"""
Data fetch — throttled SEQUENTIAL yfinance calls (Section 8.3 decision).

Deliberately NOT using yf.download() with a ticker list + threads=True:
that still fires one request per ticker under the hood, just concurrently,
which is higher rate-limit risk against an unofficial/unpublished-limit
data source, not lower. A plain for-loop with a small delay between calls
is the safer, more controllable pattern for our traffic level.

Caching: the shared TTL cache (Section 8.2) is implemented in app.py as a
module-level dict, not here — this module only does the raw fetch.
"""
import time
import pandas as pd
import yfinance as yf

from config import yf_symbol

FETCH_DELAY_SECONDS = 0.3  # throttle between sequential requests


def fetch_history(nse_symbol: str, period: str = "18mo") -> tuple[pd.DataFrame | None, str | None]:
    """
    Fetch daily OHLCV for one symbol.
    Returns (DataFrame, None) on success, or (None, error_message) on
    failure — the error is captured (not swallowed) so a whole-universe
    failure surfaces as a specific, visible reason instead of a silent
    "0 screened" with no clue why.
    """
    try:
        ticker = yf.Ticker(yf_symbol(nse_symbol))
        df = ticker.history(period=period, interval="1d", auto_adjust=True)
        if df is None or df.empty:
            return None, "empty response"
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        return df, None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def fetch_universe(symbols: list[str], period: str = "18mo", progress_callback=None) -> tuple[dict, dict]:
    """
    Sequential, throttled fetch across the full universe.
    progress_callback(done_count, total_count, symbol) — optional, for
    the UI progress indicator (Section 8.4).
    Returns (results, failures) — failures maps symbol -> error message,
    so the caller can show *why* a symbol was skipped, not just that it was.
    """
    results: dict[str, pd.DataFrame] = {}
    failures: dict[str, str] = {}
    total = len(symbols)
    for i, sym in enumerate(symbols, start=1):
        df, err = fetch_history(sym, period=period)
        if df is not None:
            results[sym] = df
        else:
            failures[sym] = err
        if progress_callback:
            progress_callback(i, total, sym)
        if i < total:
            time.sleep(FETCH_DELAY_SECONDS)
    return results, failures