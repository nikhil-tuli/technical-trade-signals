"""
Support & Resistance — Varsity-aligned zone method (requirements doc Section 4.1).

Steps implemented:
  1. Lookback window (set by Trade Type)
  2. Candidate zone detection via fractal swing highs/lows
  3. Validation: 3-touch rule + minimum time separation between touches
  4. Zone construction (price band) + dynamic Support/Resistance classification
     based on current market price (CMP), computed fresh every run.
"""
from dataclasses import dataclass
import pandas as pd

from config import SR_ZONE_TOLERANCE_PCT


@dataclass
class SRZone:
    center_price: float
    lower: float
    upper: float
    touch_count: int
    touch_dates: list


def _find_fractal_swings(df: pd.DataFrame, width: int) -> list[tuple]:
    """
    Returns list of (index, price, 'high'|'low') for confirmed fractal
    swing points — width candles on either side must be lower/higher.
    """
    swings = []
    highs, lows = df["High"].values, df["Low"].values
    n = len(df)
    for i in range(width, n - width):
        window_h = highs[i - width:i + width + 1]
        window_l = lows[i - width:i + width + 1]
        if highs[i] == window_h.max() and (window_h == highs[i]).sum() == 1:
            swings.append((i, highs[i], "high"))
        if lows[i] == window_l.min() and (window_l == lows[i]).sum() == 1:
            swings.append((i, lows[i], "low"))
    return swings


def _cluster_touches(swings: list[tuple], df: pd.DataFrame, tolerance_pct: float,
                      min_separation_days: int) -> list[SRZone]:
    """
    Cluster swing points into zones. A zone qualifies only with >=3 touches
    that are spaced >= min_separation_days apart (closer touches collapse
    into a single counted touch).
    """
    if not swings:
        return []

    # sort by price to cluster nearby levels together
    sorted_swings = sorted(swings, key=lambda s: s[1])
    zones = []
    used = [False] * len(sorted_swings)

    for i, (idx_i, price_i, _) in enumerate(sorted_swings):
        if used[i]:
            continue
        band_lower = price_i * (1 - tolerance_pct / 100)
        band_upper = price_i * (1 + tolerance_pct / 100)
        cluster = [(idx_i, price_i)]
        used[i] = True
        for j in range(i + 1, len(sorted_swings)):
            if used[j]:
                continue
            idx_j, price_j, _ = sorted_swings[j]
            if band_lower <= price_j <= band_upper:
                cluster.append((idx_j, price_j))
                used[j] = True

        # collapse touches within min_separation_days into single counted touches
        cluster.sort(key=lambda t: t[0])
        counted_touches = []
        for idx_c, price_c in cluster:
            date_c = df.index[idx_c]
            if not counted_touches:
                counted_touches.append((idx_c, price_c, date_c))
                continue
            last_date = counted_touches[-1][2]
            gap_days = (date_c - last_date).days if hasattr(date_c, "days") else abs(idx_c - counted_touches[-1][0])
            if gap_days >= min_separation_days:
                counted_touches.append((idx_c, price_c, date_c))

        if len(counted_touches) >= 3:
            avg_price = sum(p for _, p, _ in counted_touches) / len(counted_touches)
            zones.append(SRZone(
                center_price=avg_price,
                lower=avg_price * (1 - tolerance_pct / 100),
                upper=avg_price * (1 + tolerance_pct / 100),
                touch_count=len(counted_touches),
                touch_dates=[d for _, _, d in counted_touches],
            ))
    return zones


def compute_sr_zones(df: pd.DataFrame, lookback_days: int, fractal_width: int,
                      min_touch_separation_days: int,
                      tolerance_pct: float = SR_ZONE_TOLERANCE_PCT) -> list[SRZone]:
    """
    Full pipeline: slice lookback window, detect fractal swings, cluster
    into validated 3-touch zones. Returns empty list if none qualify
    (caller/Gate 3 treats this as exclusion).
    """
    window = df.tail(lookback_days).copy() if len(df) > lookback_days else df.copy()
    if len(window) < fractal_width * 2 + 5:
        return []
    swings = _find_fractal_swings(window, fractal_width)
    return _cluster_touches(swings, window, tolerance_pct, min_touch_separation_days)


def nearest_zone(zones: list[SRZone], reference_price: float, side: str):
    """
    Find the nearest qualifying zone entirely below (side='below') or
    above (side='above') a reference price. Classification is computed
    fresh against `reference_price` every call — no fixed support/
    resistance label is stored on a zone.

    Used two ways in the revised (Varsity-aligned) logic:
      - Validating the candle-derived stop-loss: nearest support zone
        below entry (bullish) / resistance zone above entry (bearish).
      - Finding the target: nearest zone on the OPPOSITE side of entry.

    Returns None if no qualifying zone exists on that side.
    """
    if side == "below":
        candidates = [z for z in zones if z.upper < reference_price]
        return max(candidates, key=lambda z: z.center_price) if candidates else None
    else:  # "above"
        candidates = [z for z in zones if z.lower > reference_price]
        return min(candidates, key=lambda z: z.center_price) if candidates else None


def near_edge(zone: SRZone, reference_price: float) -> float:
    """
    The edge of a zone closest to `reference_price` — i.e. the first
    price level the trade would actually reach, not the zone's center
    or its far edge. Used for target price (requirements doc: "near
    edge of the zone", not center).
    """
    if zone.lower > reference_price:
        return zone.lower  # zone is above price -> near edge is its lower bound
    else:
        return zone.upper  # zone is below price -> near edge is its upper bound