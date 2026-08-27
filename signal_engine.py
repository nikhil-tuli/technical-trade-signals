"""
Signal engine — orchestrates Gates 1-4 (requirements doc Section 2),
attaches contextual layers (Section 3), and computes live signal state
(Section 5: 30-day scan lookback, no persistence/DB).
"""
from dataclasses import dataclass, field
import pandas as pd

from config import (
    TRADE_TYPE_PARAMS, SR_ZONE_TOLERANCE_PCT, VOLUME_MA_PERIOD_DEFAULT,
    MIN_RR_DEFAULT, SIGNAL_SCAN_LOOKBACK_DAYS, SR_MAX_DISTANCE_PCT_DEFAULT, SL_BUFFER_PCT,
)
from patterns import detect_patterns_on_candle, compute_candle_stop_loss_detailed
from support_resistance import compute_sr_zones, nearest_zone, near_edge
from indicators import primary_trend, confluence_check


@dataclass
class Signal:
    symbol: str
    company: str
    pattern: str
    direction: str
    formation_date: object
    entry: float
    stop_loss: float
    target: float
    rr: float
    status: str  # "active" | "stopped_out" | "target_hit"
    primary_trend: dict
    confluence: dict
    details: dict = field(default_factory=dict)


@dataclass
class ExclusionRecord:
    symbol: str
    reasons: list  # e.g. ["No candlestick pattern", "Volume below MA"]


GATE_LABELS = {
    "pattern": "No candlestick pattern",
    "volume": "Volume below MA",
    "sr": "No valid S/R zone",
    "rr": "R:R below threshold",
}


def _volume_confirmed(df: pd.DataFrame, idx: int, ma_period: int) -> bool:
    if idx < ma_period:
        return False
    vol_ma = df["Volume"].iloc[idx - ma_period:idx].mean()
    return df["Volume"].iloc[idx] >= vol_ma


def _compute_rr(entry: float, stop: float, target: float, direction: str) -> float:
    risk = abs(entry - stop)
    reward = abs(target - entry)
    if risk == 0:
        return 0.0
    rr = reward / risk
    return round(rr, 2)


def screen_symbol(symbol: str, company: str, df: pd.DataFrame, trade_type: str,
                   volume_ma_period: int = VOLUME_MA_PERIOD_DEFAULT,
                   min_rr: float = MIN_RR_DEFAULT,
                   max_sr_distance_pct: float = SR_MAX_DISTANCE_PCT_DEFAULT) -> tuple[list[Signal], list[str]]:
    """
    Run all 4 gates for one symbol across the live-scan lookback window
    (Section 5: last SIGNAL_SCAN_LOOKBACK_DAYS trading days).
    Returns (list of qualifying Signals [possibly empty], list of
    aggregated failure reasons for this symbol across the scan).
    """
    params = TRADE_TYPE_PARAMS[trade_type]
    signals: list[Signal] = []
    failure_reasons: set = set()

    if df is None or len(df) < params["sr_lookback_days"] // 2:
        failure_reasons.add(GATE_LABELS["sr"])
        return signals, list(failure_reasons)

    scan_start = max(0, len(df) - SIGNAL_SCAN_LOOKBACK_DAYS)
    cmp = df["Close"].iloc[-1]

    any_pattern_found = False

    for idx in range(scan_start, len(df)):
        matches = detect_patterns_on_candle(df.iloc[: idx + 1], idx, params["pattern_prior_trend_lookback"])
        if not matches:
            continue
        any_pattern_found = True

        # Gate 2 — volume
        if not _volume_confirmed(df, idx, volume_ma_period):
            failure_reasons.add(GATE_LABELS["volume"])
            continue

        # Gate 3 — S/R zone (computed once per symbol scan iteration is
        # cheap enough at this universe size; zones recomputed using data
        # up to this candle to avoid lookahead)
        zones = compute_sr_zones(
            df.iloc[: idx + 1],
            lookback_days=params["sr_lookback_days"],
            fractal_width=params["fractal_width"],
            min_touch_separation_days=params["min_touch_separation_days"],
            tolerance_pct=SR_ZONE_TOLERANCE_PCT,
        )
        if not zones:
            failure_reasons.add(GATE_LABELS["sr"])
            continue

        entry_price = df["Close"].iloc[idx]
        vol_today = df["Volume"].iloc[idx]
        vol_ma_value = df["Volume"].iloc[idx - volume_ma_period:idx].mean()

        for match in matches:
            # SL now comes from the CANDLE, not from S/R (Varsity-aligned
            # revision) — S/R only validates it below.
            sl_calc = compute_candle_stop_loss_detailed(match)
            candle_sl = sl_calc["buffered"]

            # Nearest zone on the RISK side of entry (support below entry
            # for a bullish trade, resistance above entry for bearish).
            risk_side = "below" if match.direction == "bullish" else "above"
            validation_zone = nearest_zone(zones, entry_price, risk_side)
            if validation_zone is None:
                failure_reasons.add(GATE_LABELS["sr"])
                continue

            # Proximity check is candle-SL <-> S/R zone, NOT entry <-> zone.
            # No fallback to a further zone if this fails — reject outright
            # and move on, per Varsity's rule ("stop evaluating, move to
            # next chart").
            sl_distance_pct = abs(candle_sl - validation_zone.center_price) / candle_sl * 100
            if sl_distance_pct > max_sr_distance_pct:
                failure_reasons.add(GATE_LABELS["sr"])
                continue

            # Target: nearest zone on the OPPOSITE side of entry, using its
            # near edge (first price level reached), not center or far edge.
            reward_side = "above" if match.direction == "bullish" else "below"
            target_zone = nearest_zone(zones, entry_price, reward_side)
            if target_zone is None:
                failure_reasons.add(GATE_LABELS["sr"])
                continue
            target_price = near_edge(target_zone, entry_price)

            rr = _compute_rr(entry_price, candle_sl, target_price, match.direction)
            if rr < min_rr:
                failure_reasons.add(GATE_LABELS["rr"])
                continue

            # All 4 gates passed — determine live status against price since formation
            status = _resolve_status(df, idx, candle_sl, target_price, match.direction)
            if status != "active":
                continue  # per Section 5: only Active signals are shown

            trend_info = primary_trend(df.iloc[: idx + 1], params["primary_trend_ma"])
            conf_info = confluence_check(df.iloc[: idx + 1], match.direction)

            prior_lookback = params["pattern_prior_trend_lookback"]
            prior_trend_dates = None
            if match.prior_trend_required != "none":
                prior_trend_dates = {
                    "start": df.index[max(0, idx - prior_lookback)],
                    "end": df.index[idx - 1],
                    "days": prior_lookback,
                }

            signals.append(Signal(
                symbol=symbol, company=company, pattern=match.pattern,
                direction=match.direction, formation_date=df.index[idx],
                entry=round(entry_price, 2), stop_loss=round(candle_sl, 2),
                target=round(target_price, 2), rr=rr, status="active",
                primary_trend=trend_info, confluence=conf_info,
                details={
                    "candle": match.detail,
                    "trade_type": trade_type,
                    "prior_trend_lookback": prior_lookback,
                    "prior_trend_required": match.prior_trend_required,
                    "prior_trend_dates": prior_trend_dates,
                    "volume_today": round(vol_today, 0),
                    "volume_ma": round(vol_ma_value, 0),
                    "volume_ma_period": volume_ma_period,
                    "volume_ratio": round(vol_today / vol_ma_value, 2),
                    "sl_raw": round(sl_calc["raw"], 2),
                    "sl_buffer_pct": SL_BUFFER_PCT,
                    "sr_validation_zone_touches": validation_zone.touch_count,
                    "sr_validation_zone_lower": round(validation_zone.lower, 2),
                    "sr_validation_zone_upper": round(validation_zone.upper, 2),
                    "sr_validation_distance_pct": round(sl_distance_pct, 2),
                    "sr_validation_last_touch": max(validation_zone.touch_dates),
                    "sr_target_zone_touches": target_zone.touch_count,
                    "sr_target_zone_lower": round(target_zone.lower, 2),
                    "sr_target_zone_upper": round(target_zone.upper, 2),
                    "sr_target_last_touch": max(target_zone.touch_dates),
                    "min_rr_threshold": min_rr,
                    "max_sr_distance_threshold": max_sr_distance_pct,
                },
            ))

    if not any_pattern_found:
        failure_reasons.add(GATE_LABELS["pattern"])

    return signals, list(failure_reasons)


def _resolve_status(df: pd.DataFrame, formed_idx: int, stop: float, target: float, direction: str) -> str:
    """
    Section 5 — live status check: has price closed beyond stop or target
    since formation? Checked candle-by-candle forward from formation.
    """
    for i in range(formed_idx + 1, len(df)):
        c = df["Close"].iloc[i]
        if direction == "bullish":
            if c <= stop:
                return "stopped_out"
            if c >= target:
                return "target_hit"
        else:
            if c >= stop:
                return "stopped_out"
            if c <= target:
                return "target_hit"
    return "active"


def run_screen(universe: dict[str, pd.DataFrame], company_map: dict[str, str], trade_type: str,
               volume_ma_period: int = VOLUME_MA_PERIOD_DEFAULT,
               min_rr: float = MIN_RR_DEFAULT,
               max_sr_distance_pct: float = SR_MAX_DISTANCE_PCT_DEFAULT) -> tuple[list[Signal], list[ExclusionRecord]]:
    """
    Top-level entry point: screens every symbol in `universe`
    (symbol -> OHLCV DataFrame, already fetched), returns qualifying
    Active signals + per-symbol exclusion records (Section 6.5).
    """
    all_signals: list[Signal] = []
    exclusions: list[ExclusionRecord] = []

    for symbol, df in universe.items():
        signals, reasons = screen_symbol(symbol, company_map.get(symbol, symbol), df, trade_type,
                                          volume_ma_period, min_rr, max_sr_distance_pct)
        all_signals.extend(signals)
        if not signals and reasons:
            exclusions.append(ExclusionRecord(symbol=symbol, reasons=reasons))

    all_signals.sort(key=lambda s: s.formation_date, reverse=True)
    return all_signals, exclusions