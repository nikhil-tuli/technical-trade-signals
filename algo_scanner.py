"""
Algo Signals scanner — high-volume breakout followed by a retest of the
breakout candle's midpoint. Pure pandas/numpy, no Streamlit dependency.

Rules (see README / "How this works" tab):
  * Only COMPLETED daily candles are used. A candle dated today (IST) is
    dropped if it is fetched before 16:00 IST.
  * The NEWEST candle (searching back from the one before the latest, to at
    most ALGO_MAX_BREAKOUT_AGE candles ago) that passes the breakout test
    is THE breakout candle. Older candidates are never examined — if the
    newest one fails a later step the stock is rejected.
  * One result per stock.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from config import (
    ALGO_VOLUME_LOOKBACK, ALGO_VOLUME_MULTIPLIER, ALGO_PRICE_LOOKBACK,
    ALGO_MAX_BREAKOUT_AGE, ALGO_MIDPOINT_TOLERANCE_PCT, ALGO_MIN_CANDLES,
    ALGO_CANDLE_FINAL_HOUR_IST, NIFTY_100_MAP, NIFTY_500_MAP,
)

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
_COLS = ["Open", "High", "Low", "Close", "Volume"]


def now_ist() -> dt.datetime:
    return dt.datetime.now(IST)


def data_session_key(now: dt.datetime | None = None) -> dt.date:
    """Date of the most recent completed market session as of `now` (IST).
    Before the 16:00 cutoff today's session isn't complete; weekends roll
    back to Friday. Holidays aren't modelled (cache just refreshes once
    on the next calendar session key, which is harmless)."""
    now = (now or now_ist()).astimezone(IST)
    d = now.date()
    if now.hour < ALGO_CANDLE_FINAL_HOUR_IST:
        d -= dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def normalize_candles(df: pd.DataFrame | None) -> pd.DataFrame:
    """Numeric OHLCV, sorted oldest-first, NaN rows dropped, tz stripped."""
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=_COLS)
    out = df[[c for c in _COLS if c in df.columns]].copy()
    if len(out.columns) != len(_COLS):
        return pd.DataFrame(columns=_COLS)
    out = out.apply(pd.to_numeric, errors="coerce")
    idx = pd.to_datetime(out.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    out.index = idx.normalize()
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out.dropna()


def drop_incomplete_last_candle(df: pd.DataFrame, now: dt.datetime | None = None) -> pd.DataFrame:
    """Drop the last candle if it is dated today (IST) and it is before 16:00 IST."""
    if df.empty:
        return df
    now = (now or now_ist()).astimezone(IST)
    if df.index[-1].date() == now.date() and now.hour < ALGO_CANDLE_FINAL_HOUR_IST:
        return df.iloc[:-1]
    return df


def scan_symbol(symbol: str, raw: pd.DataFrame, company_name: str = "",
                now: dt.datetime | None = None) -> dict | None:
    """Return a result dict if `symbol` currently shows a breakout retest, else None."""
    df = drop_incomplete_last_candle(normalize_candles(raw), now)
    n = len(df)
    if n < ALGO_MIN_CANDLES:
        return None

    o, h, l, c, v = (df[k].to_numpy(dtype=float) for k in ("Open", "High", "Low", "Close", "Volume"))
    last = n - 1
    vl, pl = ALGO_VOLUME_LOOKBACK, ALGO_PRICE_LOOKBACK

    lowest = max(vl, pl, last - ALGO_MAX_BREAKOUT_AGE)
    b = None
    for i in range(last - 1, lowest - 1, -1):
        avg_vol = v[i - vl:i].mean()
        if not avg_vol > 0:
            continue
        prev_high = h[i - pl:i].max()
        if c[i] > o[i] and v[i] >= ALGO_VOLUME_MULTIPLIER * avg_vol and c[i] > prev_high:
            b = i
            break
    if b is None:
        return None

    # Newest breakout candle is the only one evaluated from here on.
    avg_vol = v[b - vl:b].mean()
    prev_high = float(h[b - pl:b].max())
    max_after = float(h[b + 1:last + 1].max())
    if not max_after > h[b]:
        return None

    mid = (h[b] + l[b]) / 2
    cur = float(c[last])
    distance = (cur - mid) / mid * 100
    age = last - b
    if abs(distance) > ALGO_MIDPOINT_TOLERANCE_PCT or age > ALGO_MAX_BREAKOUT_AGE:
        return None

    return {
        "symbol": symbol,
        "company_name": company_name,
        "current_price": cur,
        "breakout_date": df.index[b].date().isoformat(),
        "b_index": int(b),
        "days_since": int(age),
        "breakout_low": float(l[b]),
        "breakout_high": float(h[b]),
        "midpoint": float(mid),
        "distance_from_midpoint": float(distance),
        "vol_multiple": float(v[b] / avg_vol),
        "prev_high": prev_high,
        "max_price_after": max_after,
        "return_from_close_to_sub_high": float((max_after - c[b]) / c[b] * 100),
        "retracement_high": float((cur - max_after) / max_after * 100),
        "candles": df,
    }


def scan_universe(price_data: dict[str, pd.DataFrame], progress_callback=None,
                  now: dt.datetime | None = None) -> tuple[list[dict], int]:
    """Scan every fetched symbol. Returns (sorted results, number scanned).
    progress_callback(done, total, matches_so_far)."""
    names = {**NIFTY_500_MAP, **NIFTY_100_MAP}
    results: list[dict] = []
    total = len(price_data)
    for k, (sym, raw) in enumerate(price_data.items(), start=1):
        try:
            r = scan_symbol(sym, raw, names.get(sym, ""), now)
        except Exception:
            r = None
        if r:
            results.append(r)
        if progress_callback:
            progress_callback(k, total, len(results))
    results.sort(key=lambda r: (r["days_since"], abs(r["distance_from_midpoint"]), r["symbol"]))
    return results, total


def results_to_table(results: list[dict]) -> pd.DataFrame:
    """Display table (Rank, Symbol, ...). Dates are real dates for DateColumn."""
    rows = [{
        "Rank": i,
        "Symbol": r["symbol"],
        "Current Price": r["current_price"],
        "Breakout Date": dt.date.fromisoformat(r["breakout_date"]),
        "Age": r["days_since"],
        "Breakout Vol": r["vol_multiple"],
        "Retest Distance": r["distance_from_midpoint"],
        "Peak Gains": r["return_from_close_to_sub_high"],
        "Retracement": r["retracement_high"],
    } for i, r in enumerate(results, start=1)]
    return pd.DataFrame(rows, columns=[
        "Rank", "Symbol", "Current Price", "Breakout Date", "Age",
        "Breakout Vol", "Retest Distance", "Peak Gains", "Retracement"])
