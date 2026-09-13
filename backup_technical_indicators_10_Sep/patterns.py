"""
Candlestick pattern detection — Gate 1 of the signal engine.
Implements the pattern table from requirements doc Section 2, Gate 1.

Each detector returns a dict with match info (or None) including the
prior-trend check used, so Details (Section 6.3) can show it later.
"""
from dataclasses import dataclass
from typing import Optional
import pandas as pd

from config import MARUBOZU_SHADOW_TOLERANCE_PCT, SL_BUFFER_PCT


@dataclass
class PatternMatch:
    pattern: str
    direction: str  # "bullish" | "bearish"
    prior_trend_required: str  # "up" | "down" | "none"
    prior_trend_confirmed: bool
    detail: dict  # shape ratios etc. for Details view


def _candle_parts(row) -> dict:
    o, h, l, c = row["Open"], row["High"], row["Low"], row["Close"]
    rng = max(h - l, 1e-9)
    body = abs(c - o)
    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - l
    return {
        "open": o, "high": h, "low": l, "close": c,
        "range": rng, "body": body,
        "body_pct": body / rng * 100,
        "upper_shadow_pct": upper_shadow / rng * 100,
        "lower_shadow_pct": lower_shadow / rng * 100,
        "is_green": c > o,
        "is_red": c < o,
    }


def _prior_trend(df: pd.DataFrame, idx: int, lookback: int) -> str:
    """
    Cheap prior-trend check used only for pattern qualification (Gate 1).
    Distinct from Primary Trend (Section 3.1, MA-based).
    Returns 'up', 'down', or 'flat'.
    """
    start = max(0, idx - lookback)
    window = df.iloc[start:idx]
    if len(window) < 2:
        return "flat"
    change_pct = (window["Close"].iloc[-1] - window["Close"].iloc[0]) / window["Close"].iloc[0] * 100 #compares difference between first close and last close of the window
    if change_pct > 1.0:
        return "up"
    if change_pct < -1.0:
        return "down"
    return "flat"


def detect_patterns_on_candle(df: pd.DataFrame, idx: int, prior_trend_lookback: int) -> list[PatternMatch]:
    """
    Check all pattern rules against df.iloc[idx] (and preceding candles for
    multi-candle patterns). Returns a list — more than one match is allowed
    and both are surfaced (requirements doc: no precedence logic).
    """
    matches: list[PatternMatch] = []
    if idx < 2:
        return matches

    cur = _candle_parts(df.iloc[idx])
    prev = _candle_parts(df.iloc[idx - 1])
    trend = _prior_trend(df, idx, prior_trend_lookback)

    # --- Marubozu (either direction, no prior trend requirement) ---
    if cur["upper_shadow_pct"] <= MARUBOZU_SHADOW_TOLERANCE_PCT and cur["lower_shadow_pct"] <= MARUBOZU_SHADOW_TOLERANCE_PCT:
        if cur["is_green"]:
            matches.append(PatternMatch("Bullish Marubozu", "bullish", "none", True, cur))
        elif cur["is_red"]:
            matches.append(PatternMatch("Bearish Marubozu", "bearish", "none", True, cur))

    # --- Hammer (bullish, requires prior downtrend) ---
    if cur["lower_shadow_pct"] >= 2 * cur["body_pct"] and cur["upper_shadow_pct"] <= cur["body_pct"] * 0.5 and cur["body_pct"] > 0:
        matches.append(PatternMatch("Hammer", "bullish", "down", trend == "down", cur))

    # --- Shooting Star (bearish, requires prior uptrend) ---
    if cur["upper_shadow_pct"] >= 2 * cur["body_pct"] and cur["lower_shadow_pct"] <= cur["body_pct"] * 0.5 and cur["body_pct"] > 0:
        matches.append(PatternMatch("Shooting Star", "bearish", "up", trend == "up", cur))

    # --- Bullish Engulfing (requires prior downtrend) ---
    if prev["is_red"] and cur["is_green"] and cur["open"] <= prev["close"] and cur["close"] >= prev["open"]:
        matches.append(PatternMatch("Bullish Engulfing", "bullish", "down", trend == "down", {"cur": cur, "prev": prev}))

    # --- Bearish Engulfing (requires prior uptrend) ---
    if prev["is_green"] and cur["is_red"] and cur["open"] >= prev["close"] and cur["close"] <= prev["open"]:
        matches.append(PatternMatch("Bearish Engulfing", "bearish", "up", trend == "up", {"cur": cur, "prev": prev}))

    # --- Morning Star (3-candle, bullish, requires prior downtrend) ---
    if idx >= 3:
        c1 = _candle_parts(df.iloc[idx - 2])
        c2 = _candle_parts(df.iloc[idx - 1])
        c3 = cur
        if (c1["is_red"] and c1["body_pct"] > 50
                and c2["body_pct"] < 30
                and c3["is_green"] and c3["close"] > (c1["open"] + c1["close"]) / 2):
            matches.append(PatternMatch("Morning Star", "bullish", "down", trend == "down",
                                         {"c1": c1, "c2": c2, "c3": c3}))

    # --- Evening Star (3-candle, bearish, requires prior uptrend) ---
    if idx >= 3:
        c1 = _candle_parts(df.iloc[idx - 2])
        c2 = _candle_parts(df.iloc[idx - 1])
        c3 = cur
        if (c1["is_green"] and c1["body_pct"] > 50
                and c2["body_pct"] < 30
                and c3["is_red"] and c3["close"] < (c1["open"] + c1["close"]) / 2):
            matches.append(PatternMatch("Evening Star", "bearish", "up", trend == "up",
                                         {"c1": c1, "c2": c2, "c3": c3}))

    # Only return matches whose prior-trend precondition is satisfied
    # (requirements doc: a pattern only qualifies if its precondition is met)
    return [m for m in matches if m.prior_trend_confirmed]


def compute_candle_stop_loss_detailed(match: PatternMatch) -> dict:
    """
    Same logic as compute_candle_stop_loss(), but returns both the raw
    (pre-buffer) candle price and the buffered final stop-loss — needed
    for a transparent Details view showing exactly how the SL was derived.
    """
    d = match.detail

    if match.pattern in ("Bullish Marubozu", "Hammer"):
        raw = d["low"]
    elif match.pattern in ("Bearish Marubozu", "Shooting Star"):
        raw = d["high"]
    elif match.pattern == "Bullish Engulfing":
        raw = min(d["cur"]["low"], d["prev"]["low"])
    elif match.pattern == "Bearish Engulfing":
        raw = max(d["cur"]["high"], d["prev"]["high"])
    elif match.pattern == "Morning Star":
        raw = min(d["c1"]["low"], d["c2"]["low"], d["c3"]["low"])
    elif match.pattern == "Evening Star":
        raw = max(d["c1"]["high"], d["c2"]["high"], d["c3"]["high"])
    else:
        raise ValueError(f"Unknown pattern for SL computation: {match.pattern}")

    buffered = raw * (1 - SL_BUFFER_PCT / 100) if match.direction == "bullish" else raw * (1 + SL_BUFFER_PCT / 100)
    return {"raw": raw, "buffered": buffered}


def compute_candle_stop_loss(match: PatternMatch) -> float:
    """
    Candle-derived stop-loss, per pattern (Varsity-aligned — SL comes from
    the candle, S/R only validates it, per requirements doc revision).
    Returns the BUFFERED price (raw candle low/high +/- SL_BUFFER_PCT),
    ready to use directly as the trade's stop-loss.

    Bullish patterns -> SL below the relevant low.
    Bearish patterns -> SL above the relevant high.
    """
    return compute_candle_stop_loss_detailed(match)["buffered"]