"""
Technical indicators for the Confluence layer (Section 3.3) and
Primary Trend (Section 3.1). All computed with standard/Wilder conventions.
"""
import pandas as pd
import numpy as np

from config import (
    RSI_PERIOD, MACD_FAST, MACD_SLOW, MACD_SIGNAL,
    SUPERTREND_PERIOD, SUPERTREND_MULTIPLIER, AROON_PERIOD,
    TREND_SLOPE_LOOKBACK_DAYS, SIDEWAYS_FLIP_WINDOW,
)


def rsi(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    """Wilder-smoothed RSI (not a simple rolling mean — see chat discussion)."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(close: pd.Series, fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def supertrend(df: pd.DataFrame, period: int = SUPERTREND_PERIOD, multiplier: float = SUPERTREND_MULTIPLIER):
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    hl2 = (high + low) / 2
    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr

    direction = pd.Series(index=df.index, dtype="object")
    final_upper = upper_band.copy()
    final_lower = lower_band.copy()

    for i in range(1, len(df)):
        if close.iloc[i - 1] <= final_upper.iloc[i - 1]:
            final_upper.iloc[i] = min(upper_band.iloc[i], final_upper.iloc[i - 1])
        else:
            final_upper.iloc[i] = upper_band.iloc[i]

        if close.iloc[i - 1] >= final_lower.iloc[i - 1]:
            final_lower.iloc[i] = max(lower_band.iloc[i], final_lower.iloc[i - 1])
        else:
            final_lower.iloc[i] = lower_band.iloc[i]

        if close.iloc[i] <= final_upper.iloc[i]:
            direction.iloc[i] = "bearish"
        else:
            direction.iloc[i] = "bullish"

    return direction


def aroon(df: pd.DataFrame, period: int = AROON_PERIOD):
    high, low = df["High"], df["Low"]
    aroon_up = high.rolling(period + 1).apply(lambda x: x.argmax() / period * 100, raw=True)
    aroon_down = low.rolling(period + 1).apply(lambda x: x.argmin() / period * 100, raw=True)
    return aroon_up, aroon_down


def primary_trend(df: pd.DataFrame, ma_period: int) -> dict:
    """
    Section 3.1 — Primary Trend, MA-based.
    Up: close > MA and MA slope rising over TREND_SLOPE_LOOKBACK_DAYS.
    Down: close < MA and MA slope falling.
    Sideways: price-vs-MA relationship flipped more than once in the
    last SIDEWAYS_FLIP_WINDOW candles.

    Returns enough raw values (not just the final label) to build a
    fully descriptive Details explanation — e.g. "price ₹X is above the
    N-day MA ₹Y, which has risen from ₹Z over the last M days."
    """
    ma = df["Close"].rolling(ma_period).mean()
    close = df["Close"]

    if len(df) < ma_period + max(TREND_SLOPE_LOOKBACK_DAYS, SIDEWAYS_FLIP_WINDOW) + 1:
        return {
            "trend": "Unknown", "ma_value": None, "slope": None, "flip_count": None,
            "close_now": None, "ma_then": None, "ma_period": ma_period,
            "slope_lookback_days": TREND_SLOPE_LOOKBACK_DAYS,
            "sideways_flip_window": SIDEWAYS_FLIP_WINDOW,
        }

    ma_now = ma.iloc[-1]
    ma_then = ma.iloc[-1 - TREND_SLOPE_LOOKBACK_DAYS]
    slope_rising = ma_now > ma_then
    slope_falling = ma_now < ma_then

    recent_relation = (close.iloc[-SIDEWAYS_FLIP_WINDOW:] > ma.iloc[-SIDEWAYS_FLIP_WINDOW:]).astype(int)
    flips = (recent_relation.diff().abs() == 1).sum()

    if flips > 1:
        trend = "Sideways"
    elif close.iloc[-1] > ma_now and slope_rising:
        trend = "Up"
    elif close.iloc[-1] < ma_now and slope_falling:
        trend = "Down"
    else:
        trend = "Sideways"

    return {
        "trend": trend,
        "ma_value": round(ma_now, 2),
        "slope": "rising" if slope_rising else ("falling" if slope_falling else "flat"),
        "flip_count": int(flips),
        "close_now": round(close.iloc[-1], 2),
        "ma_then": round(ma_then, 2),
        "ma_period": ma_period,
        "slope_lookback_days": TREND_SLOPE_LOOKBACK_DAYS,
        "sideways_flip_window": SIDEWAYS_FLIP_WINDOW,
    }


def confluence_check(df: pd.DataFrame, direction: str) -> dict:
    """
    Section 3.3 — indicator confluence. Evaluates RSI, MACD, Supertrend,
    Aroon for directional agreement with the signal. Returns individual
    readings + confirming count (informational only — never gates).
    """
    close = df["Close"]
    r = rsi(close).iloc[-1]
    macd_line, signal_line, _ = macd(close)
    macd_bullish = macd_line.iloc[-1] > signal_line.iloc[-1]
    st_dir = supertrend(df).iloc[-1]
    aroon_up, aroon_down = aroon(df)
    aroon_bullish = aroon_up.iloc[-1] > aroon_down.iloc[-1]

    if direction == "bullish":
        checks = {
            "RSI": r > 50 if not pd.isna(r) else False,
            "MACD": macd_bullish,
            "Supertrend": st_dir == "bullish",
            "Aroon": aroon_bullish,
        }
    else:
        checks = {
            "RSI": r < 50 if not pd.isna(r) else False,
            "MACD": not macd_bullish,
            "Supertrend": st_dir == "bearish",
            "Aroon": not aroon_bullish,
        }

    confirming = sum(checks.values())
    return {
        "confirming_count": confirming,
        "total": 4,
        "checks": checks,
        "raw_values": {
            "RSI": round(r, 1) if not pd.isna(r) else None,
            "MACD": "bullish" if macd_bullish else "bearish",
            "Supertrend": st_dir,
            "Aroon": "up" if aroon_bullish else "down",
        },
    }