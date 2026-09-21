"""
Momentum Screener engine — ranking/filtering logic only, no UI, no
network calls (price_data is passed in already fetched, via the SAME
data_fetch.fetch_universe() used by the Signal Screener — no separate
fetch function needed since fetch_universe() is already symbol-agnostic).

Deliberately does NOT reuse indicators.primary_trend(): that function
computes slope direction + sideways-flip classification for the Signal
Screener's gated pattern logic. The momentum trend filter is simpler by
design (Section 3 of the requirements discussion — single condition,
"Price > N-DMA", no slope check) and reusing primary_trend would force
this module to depend on TREND_SLOPE_LOOKBACK_DAYS / SIDEWAYS_FLIP_WINDOW
semantics that don't apply here. price_above_dma() below is intentionally
its own small function.

Also does NOT duplicate the Nifty 500 symbol list: callers pass in
whatever price_data dict they fetched (keyed by the same NSE symbols
used everywhere else — config.NIFTY_500_MAP / nse_master_data.py).
"""

import math

import pandas as pd
import numpy as np

from config import (
    MOMENTUM_RETURN_WINDOWS,
    MOMENTUM_LOOKBACK_MONTHS,
    MOMENTUM_VOLUME_BASELINE_DAYS_DEFAULT,
    MOMENTUM_VOLUME_RECENT_DAYS,
    MOMENTUM_LIQUIDITY_LOOKBACK_DAYS,
    MOMENTUM_RISK_FREE_RATE_PCT,
)
import nse_master_data

TRADING_DAYS_PER_MONTH = 21  # approx, consistent with how the 12mo window is sliced


class InsufficientDataError(Exception):
    """Raised when a DataFrame has too few rows for the requested window —
    callers should catch this per-symbol and skip, not let one short
    history crash the whole ranking table."""


MIN_WINDOW_COVERAGE = 0.9  # sliced data must cover >=90% of the requested window


def _window_slice(df: pd.DataFrame, trading_days: int, exclude_last_month: bool = False) -> pd.DataFrame:
    """
    Returns the trailing `trading_days` of df, optionally dropping the
    most recent calendar month (Section 'exclude last month' toggle)
    first. Returns an EMPTY DataFrame (not a short one) if there isn't
    at least MIN_WINDOW_COVERAGE of the requested window available —
    callers use `sliced.empty` as the insufficient-data signal instead
    of computing a misleadingly-labeled "12mo return" off a fraction of
    that much history (e.g. a stock listed 3 weeks ago).
    """
    if exclude_last_month:
        df = df.iloc[: -TRADING_DAYS_PER_MONTH] if len(df) > TRADING_DAYS_PER_MONTH else df.iloc[0:0]
    sliced = df.tail(trading_days)
    if len(sliced) < trading_days * MIN_WINDOW_COVERAGE:
        return sliced.iloc[0:0]
    return sliced


def price_points(df: pd.DataFrame, exclude_last_month: bool = False) -> dict:
    """
    Returns the actual (price, date) pairs behind the returns columns —
    today's close, and the close N trading days ago for each window in
    MOMENTUM_RETURN_WINDOWS plus the 12-month window — so the drill-down
    view can show real numbers next to the calculated % figures (for
    verification/credibility, not for ranking). Uses the exact same
    indexing as n_day_return_pct() / lookback_return_pct(), so these
    numbers always match whatever the table currently shows for the
    same stock and the same exclude_last_month setting.

    Returns {"today": (price, date), 30: (price, date), ..., "12mo": (price, date)}.
    A window with insufficient history gets (None, None) rather than
    being omitted, so callers can render a consistent row set.
    """
    points: dict = {}
    if len(df) < 1:
        return points

    points["today"] = (round(float(df["Close"].iloc[-1]), 2), df.index[-1])

    for w in MOMENTUM_RETURN_WINDOWS:
        if len(df) >= w + 1:
            points[w] = (round(float(df["Close"].iloc[-w - 1]), 2), df.index[-w - 1])
        else:
            points[w] = (None, None)

    window_days = MOMENTUM_LOOKBACK_MONTHS * TRADING_DAYS_PER_MONTH
    sliced = _window_slice(df, window_days + 1, exclude_last_month=exclude_last_month)
    if len(sliced) >= 2:
        points["12mo"] = (round(float(sliced["Close"].iloc[0]), 2), sliced.index[0])
    else:
        points["12mo"] = (None, None)

    return points


def n_day_return_pct(df: pd.DataFrame, window_days: int) -> float | None:
    """% change in Close over the trailing `window_days` trading days.
    Returns None (not NaN) if there isn't enough history — callers can
    render this as a blank cell rather than a misleading 0%."""
    if len(df) < window_days + 1:
        return None
    close = df["Close"]
    start, end = close.iloc[-window_days - 1], close.iloc[-1]
    if start == 0:
        return None
    return round((end / start - 1) * 100, 2)


def lookback_return_pct(df: pd.DataFrame, months: int = MOMENTUM_LOOKBACK_MONTHS,
                         exclude_last_month: bool = False) -> tuple[float | None, float | None]:
    """Returns (absolute_rupee_change, pct_change) over the trailing
    `months`, with the optional exclude-last-month toggle applied
    BEFORE the window is measured (i.e. it's a 11mo return ending one
    month ago, not a 12mo return with a gap in the middle)."""
    window_days = months * TRADING_DAYS_PER_MONTH
    sliced = _window_slice(df, window_days + 1, exclude_last_month=exclude_last_month)
    if len(sliced) < 2:  # covers both "empty" (insufficient coverage) and near-empty
        return None, None
    start, end = sliced["Close"].iloc[0], sliced["Close"].iloc[-1]
    if start == 0:
        return None, None
    abs_change = round(end - start, 2)
    pct_change = round((end / start - 1) * 100, 2)
    return abs_change, pct_change


def _daily_returns(df: pd.DataFrame, months: int = MOMENTUM_LOOKBACK_MONTHS,
                    exclude_last_month: bool = False) -> pd.Series:
    """Day-to-day % price changes over the trailing `months` window
    (same windowing as lookback_return_pct). Shared by sharpe_ratio,
    hit_rate_pct, and volatility_pct so the "what counts as the window"
    logic lives in exactly one place. Empty Series if insufficient data."""
    window_days = months * TRADING_DAYS_PER_MONTH
    sliced = _window_slice(df, window_days + 1, exclude_last_month=exclude_last_month)
    if len(sliced) < 3:
        return pd.Series(dtype=float)
    return sliced["Close"].pct_change().dropna()


TRADING_DAYS_PER_YEAR = 252  # for annualizing daily volatility in sharpe_ratio


def sharpe_ratio(df: pd.DataFrame, months: int = MOMENTUM_LOOKBACK_MONTHS,
                  exclude_last_month: bool = False,
                  risk_free_rate_pct: float = MOMENTUM_RISK_FREE_RATE_PCT) -> float | None:
    """
    (12mo return % − risk-free rate %) ÷ annualized volatility (daily
    std dev x sqrt(252)). This is the textbook Sharpe ratio definition
    (Sharpe, 1966) — return in excess of a risk-free benchmark, per unit
    of volatility. Replaces the earlier "Ret/vol" metric, which was this
    exact formula with the risk-free rate silently assumed to be zero;
    that made a barely-positive, low-volatility stock look artificially
    attractive when in reality it hadn't even cleared a risk-free
    T-bill. risk_free_rate_pct defaults to the config constant — a
    manually-refreshed value (see MOMENTUM_RISK_FREE_RATE_ASOF in
    config.py), not a live rate fetch.
    None if too little data or zero volatility (flat/illiquid series).
    """
    daily_returns = _daily_returns(df, months=months, exclude_last_month=exclude_last_month)
    if daily_returns.empty:
        return None
    vol = daily_returns.std()
    if vol is None or vol == 0 or np.isnan(vol):
        return None
    _, pct_return = lookback_return_pct(df, months=months, exclude_last_month=exclude_last_month)
    if pct_return is None:
        return None
    annualized_vol_pct = vol * 100 * math.sqrt(TRADING_DAYS_PER_YEAR)
    excess_return_pct = pct_return - risk_free_rate_pct
    return round(excess_return_pct / annualized_vol_pct, 2)


# DISABLED — the "Volatility %" column and "Max volatility %" filter were
# removed as redundant once Sharpe ratio was added (Sharpe already
# captures risk-adjusted return; sharpe_ratio() computes volatility
# internally and does NOT call this function). Commented out rather than
# deleted in case a pure "filter by choppiness regardless of return"
# control is wanted again later.
#
# def volatility_pct(df: pd.DataFrame, months: int = MOMENTUM_LOOKBACK_MONTHS,
#                     exclude_last_month: bool = False) -> float | None:
#     """The standard deviation of day-to-day % price changes over the
#     trailing `months` window, as a percentage. NOT annualized here (no
#     sqrt(252) scaling) — this is the raw daily std dev over the window."""
#     daily_returns = _daily_returns(df, months=months, exclude_last_month=exclude_last_month)
#     if daily_returns.empty:
#         return None
#     std = daily_returns.std()
#     if std is None or np.isnan(std):
#         return None
#     return round(std * 100, 2)


def hit_rate_pct(df: pd.DataFrame, months: int = MOMENTUM_LOOKBACK_MONTHS,
                  exclude_last_month: bool = False) -> float | None:
    """% of positive-return trading days over the window."""
    daily_returns = _daily_returns(df, months=months, exclude_last_month=exclude_last_month)
    if daily_returns.empty:
        return None
    return round((daily_returns > 0).mean() * 100, 1)


def price_above_dma(df: pd.DataFrame, dma_period: int) -> bool | None:
    """Single-condition trend filter: is the latest close above its
    N-day moving average? None if not enough history to compute the MA."""
    if len(df) < dma_period:
        return None
    ma = df["Close"].rolling(dma_period).mean().iloc[-1]
    if pd.isna(ma):
        return None
    return bool(df["Close"].iloc[-1] > ma)


def current_price(df: pd.DataFrame) -> float | None:
    """Latest close price — the 'Current stock price' column."""
    if len(df) < 1:
        return None
    price = df["Close"].iloc[-1]
    return round(float(price), 2) if not pd.isna(price) else None


def dma_value(df: pd.DataFrame, dma_period: int) -> float | None:
    """The actual N-day moving average value (not the boolean trend
    check above) — the 'N-day DMA' column, shown alongside current price
    so the trend filter's basis is visible, not just its pass/fail result."""
    if len(df) < dma_period:
        return None
    ma = df["Close"].rolling(dma_period).mean().iloc[-1]
    return round(float(ma), 2) if not pd.isna(ma) else None


def week_52_high(df: pd.DataFrame, trading_days: int = 252) -> float | None:
    """Highest High price over the trailing ~52 weeks. Uses 252 trading
    days for consistency with the 12mo/252d windows used elsewhere in
    this module (a calendar-accurate 52 weeks would be ~260 trading
    days — close enough that reusing the same 252 already defined
    elsewhere was preferred over introducing a second, slightly
    different 'a year' constant).
    For a stock with LESS than 252 days of history (recently listed),
    uses whatever is available rather than returning None — this is
    then effectively an all-time high, not a true 52-week high; the
    column's tooltip says so."""
    if len(df) < 1:
        return None
    window = df.tail(trading_days)
    high = window["High"].max()
    return round(float(high), 2) if not pd.isna(high) else None


def volume_participation_pct(df: pd.DataFrame,
                              recent_days: int = MOMENTUM_VOLUME_RECENT_DAYS,
                              baseline_days: int = MOMENTUM_VOLUME_BASELINE_DAYS_DEFAULT) -> float | None:
    """10-day avg volume as a % of the baseline (default 50-day) avg
    volume. >100 = participation above the stock's own norm. Display-only
    in v1 — not a hard filter (Section 'Volume filter' decision)."""
    if len(df) < baseline_days:
        return None
    recent_avg = df["Volume"].tail(recent_days).mean()
    baseline_avg = df["Volume"].tail(baseline_days).mean()
    if baseline_avg == 0 or pd.isna(baseline_avg):
        return None
    return round((recent_avg / baseline_avg) * 100, 1)


def annual_traded_turnover_cr(df: pd.DataFrame, lookback_days: int = MOMENTUM_LIQUIDITY_LOOKBACK_DAYS) -> float | None:
    """
    ACTUAL trailing-year traded value: the SUM (not average) of daily
    turnover (Close x Volume) over the trailing `lookback_days` (default
    252, i.e. the real past year), in ₹ crore. This is the
    liquidity-floor eligibility metric.
    Deliberately a sum over the real fetched year of data, not a 30-day
    average extrapolated x252 — a real trailing total is more robust to
    one unusually active or quiet recent month skewing the figure than
    a short-window projection would be.
    """
    if len(df) < 1:
        return None
    window = df.tail(lookback_days)
    turnover = (window["Close"] * window["Volume"]).sum()
    if pd.isna(turnover):
        return None
    return round(turnover / 1e7, 2)


def compute_symbol_metrics(symbol: str, df: pd.DataFrame, dma_period: int,
                            exclude_last_month: bool = False,
                            volume_baseline_days: int = MOMENTUM_VOLUME_BASELINE_DAYS_DEFAULT) -> dict:
    """All momentum metrics for one symbol, as a flat dict — one row of
    the eventual ranking table."""
    row = {"symbol": symbol}
    for w in MOMENTUM_RETURN_WINDOWS:
        row[f"return_{w}d_pct"] = n_day_return_pct(df, w)

    abs_change, pct_change = lookback_return_pct(df, exclude_last_month=exclude_last_month)
    row["return_12mo_abs"] = abs_change
    row["return_12mo_pct"] = pct_change
    row["sharpe_ratio"] = sharpe_ratio(df, exclude_last_month=exclude_last_month)
    # row["volatility_pct"] = volatility_pct(df, exclude_last_month=exclude_last_month)  # DISABLED, see comment above
    row["hit_rate_pct"] = hit_rate_pct(df, exclude_last_month=exclude_last_month)
    row["current_price"] = current_price(df)
    row["week_52_high"] = week_52_high(df)
    row["dma_value"] = dma_value(df, dma_period)
    row["price_above_dma"] = price_above_dma(df, dma_period)
    row["volume_participation_pct"] = volume_participation_pct(df, baseline_days=volume_baseline_days)
    row["annual_traded_turnover_cr"] = annual_traded_turnover_cr(df)

    sector = nse_master_data.get_sector(symbol)
    days_listed = nse_master_data.days_listed(symbol)
    listing_date = nse_master_data.get_listing_date(symbol)
    row["sector"] = sector
    row["days_listed"] = days_listed
    row["listing_date"] = listing_date
    return row


def add_relative_momentum(table: pd.DataFrame) -> pd.DataFrame:
    """
    Adds sector_avg_return_12mo_pct and relative_to_sector_return_12mo_pct
    (the stock's own 12mo return minus its sector's average). The sector
    average is computed from the FULL table passed in — call this on the
    unfiltered, freshly-fetched universe (build_momentum_table's output),
    not on an already-filtered subset, so the benchmark reflects the
    sector as a whole rather than only the stocks that happened to pass
    other filters (a liquidity or trend filter shrinking the sector's
    sample would otherwise silently bias the average).
    Rows with no sector (e.g. Custom tickers outside Nifty 500) get NaN
    for both new columns — there's no sector to benchmark against.
    """
    result = table.copy()
    sector_avg = result.groupby("sector")["return_12mo_pct"].transform("mean")
    result["sector_avg_return_12mo_pct"] = sector_avg.round(2)
    result["relative_to_sector_return_12mo_pct"] = (result["return_12mo_pct"] - sector_avg).round(2)
    return result


def build_momentum_table(price_data: dict, dma_period: int, exclude_last_month: bool = False,
                          volume_baseline_days: int = MOMENTUM_VOLUME_BASELINE_DAYS_DEFAULT) -> pd.DataFrame:
    """
    price_data: {symbol: OHLCV DataFrame} — as returned by
    data_fetch.fetch_universe(). Symbols with no sector/listing-date
    match in nse_master_data are still included (sector/days_listed
    will be None) rather than silently dropped — filters downstream
    decide whether to exclude them, this function doesn't.
    """
    rows = [
        compute_symbol_metrics(sym, df, dma_period, exclude_last_month=exclude_last_month,
                                volume_baseline_days=volume_baseline_days)
        for sym, df in price_data.items()
        if df is not None and not df.empty
    ]
    table = pd.DataFrame(rows)
    if table.empty:
        return table
    return add_relative_momentum(table)


def build_sector_table(table: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregates a full (unfiltered) per-stock momentum table — as
    returned by build_momentum_table() — into one row per sector: the
    Sector View. MUST be called on the full fetched universe, not an
    already stock-filtered subset, so sector figures reflect the sector
    as a whole (same principle as add_relative_momentum's sector-average
    columns above).

    All aggregates are EQUAL-WEIGHTED — a plain mean/median across the
    sector's stocks, not weighted by market cap. Cap-weighting would
    need a separate market-cap fetch (yfinance .info/fast_info is a
    heavier, less reliable call than the OHLCV history already being
    pulled) and is deliberately deferred, not silently approximated;
    equal-weighting is a real, stated methodology here, not a stand-in
    for a "better" number.

    Rows with sector = None (e.g. Custom tickers outside the Nifty 500
    universe, which has no sector data for them) are EXCLUDED from the
    sector table itself — there's no sector to group them under — but
    ARE included in the universe-wide 12mo average used for the
    "vs universe" column, since that benchmark should reflect the whole
    fetched universe, not just the subset with a known sector.

    Breadth figures (stocks up, stocks above DMA) use the count of
    stocks in that sector with a NON-NULL value for that specific
    metric as the denominator — not the sector's total stock count — so
    a stock lacking enough history for a given metric is excluded from
    both the numerator and denominator, not silently counted as "not
    up" / "not above DMA".
    """
    if table.empty:
        return pd.DataFrame()

    universe_avg_12mo = table["return_12mo_pct"].mean()

    sectored = table[table["sector"].notna()]
    if sectored.empty:
        return pd.DataFrame()

    def _mean_or_none(s: pd.Series) -> float | None:
        return round(s.mean(), 2) if s.notna().any() else None

    def _median_or_none(s: pd.Series) -> float | None:
        return round(s.median(), 2) if s.notna().any() else None

    rows = []
    for sector_name, grp in sectored.groupby("sector"):
        avg_12mo = grp["return_12mo_pct"].mean()

        up_valid = grp["return_12mo_pct"].dropna()
        stocks_up_count = int((up_valid > 0).sum())
        stocks_up_pct = round(stocks_up_count / len(up_valid) * 100, 1) if len(up_valid) else None

        dma_valid = grp["price_above_dma"].dropna()
        stocks_above_dma_count = int((dma_valid == True).sum())  # noqa: E712
        stocks_above_dma_pct = round(stocks_above_dma_count / len(dma_valid) * 100, 1) if len(dma_valid) else None

        rows.append({
            "sector": sector_name,
            "avg_return_12mo_pct": round(avg_12mo, 2) if pd.notna(avg_12mo) else None,
            "med_return_12mo_pct": _median_or_none(grp["return_12mo_pct"]),
            "avg_return_30d_pct": _mean_or_none(grp["return_30d_pct"]),
            "avg_return_60d_pct": _mean_or_none(grp["return_60d_pct"]),
            "avg_return_90d_pct": _mean_or_none(grp["return_90d_pct"]),
            "avg_return_180d_pct": _mean_or_none(grp["return_180d_pct"]),
            "vs_universe_return_12mo_pct": (
                round(avg_12mo - universe_avg_12mo, 2)
                if pd.notna(avg_12mo) and pd.notna(universe_avg_12mo) else None
            ),
            "num_stocks": len(grp),
            "stocks_up_12mo_count": stocks_up_count,
            "stocks_up_12mo_pct": stocks_up_pct,
            "stocks_above_dma_count": stocks_above_dma_count,
            "stocks_above_dma_pct": stocks_above_dma_pct,
            "avg_sharpe_ratio": _mean_or_none(grp["sharpe_ratio"]),
            "avg_annual_traded_turnover_cr": _mean_or_none(grp["annual_traded_turnover_cr"]),
            "avg_relative_volume_pct": _mean_or_none(grp["volume_participation_pct"]),
        })

    return pd.DataFrame(rows)


def apply_sector_filters(sector_table: pd.DataFrame, sector: str | None = None,
                          min_avg_return_12mo_pct: float | None = None,
                          min_avg_sharpe_ratio: float | None = None) -> pd.DataFrame:
    """Eligibility filters on the SECTOR table (one row per sector) —
    distinct from apply_filters() above, which filters individual
    stocks. None means "no filter" for the two numeric thresholds,
    same convention used throughout this module."""
    df = sector_table.copy()

    if sector and sector != "All sectors":
        df = df[df["sector"] == sector]

    if min_avg_return_12mo_pct is not None:
        df = df[df["avg_return_12mo_pct"].notna() & (df["avg_return_12mo_pct"] >= min_avg_return_12mo_pct)]

    if min_avg_sharpe_ratio is not None:
        df = df[df["avg_sharpe_ratio"].notna() & (df["avg_sharpe_ratio"] >= min_avg_sharpe_ratio)]

    return df


def apply_filters(table: pd.DataFrame, sector: str | None = None,
                   min_listing_months: int | None = None,
                   liquidity_floor_cr: float | None = None,
                   min_price: float | None = None,
                   max_volatility_pct: float | None = None,
                   min_sharpe_ratio: float | None = None,
                   require_above_dma: bool = True) -> pd.DataFrame:
    """
    Hard eligibility filters (sector, listing period, liquidity, price
    floor, volatility cap, Sharpe ratio floor, trend). Volume
    participation (Relative Volume %) is intentionally NOT filtered here
    — display column only, per the requirements discussion.
    Rows with a None value for a filtered field are excluded (can't
    confirm eligibility = treated as not eligible, not silently passed).
    min_price, max_volatility_pct, and min_sharpe_ratio all treat None
    (not 0) as "no filter" — callers pass None when the UI's threshold
    is at its default/disabled state (0), not a literal 0 that would
    exclude everything. Note this means a Sharpe ratio filter of exactly
    0.0 can't be distinguished from "disabled" — same convention as the
    other 0-disables filters, kept for consistency even though 0 is a
    meaningful Sharpe value (breakeven vs. the risk-free rate).
    """
    df = table.copy()

    if sector and sector != "All sectors":
        df = df[df["sector"] == sector]

    if min_listing_months is not None:
        min_days = min_listing_months * 30
        df = df[df["days_listed"].notna() & (df["days_listed"] >= min_days)]

    if liquidity_floor_cr is not None:
        df = df[df["annual_traded_turnover_cr"].notna() & (df["annual_traded_turnover_cr"] >= liquidity_floor_cr)]

    if min_price is not None:
        df = df[df["current_price"].notna() & (df["current_price"] >= min_price)]

    if max_volatility_pct is not None:
        pass  # DISABLED — volatility_pct column removed, see momentum_engine.py comment. Parameter
        # kept in the signature (harmless no-op) rather than removed, so re-enabling later is a
        # one-line uncomment instead of a signature change everywhere this function is called.
        # df = df[df["volatility_pct"].notna() & (df["volatility_pct"] <= max_volatility_pct)]

    if min_sharpe_ratio is not None:
        df = df[df["sharpe_ratio"].notna() & (df["sharpe_ratio"] >= min_sharpe_ratio)]

    if require_above_dma:
        df = df[df["price_above_dma"] == True]  # noqa: E712 — explicit True check excludes None too

    return df


def sort_table(table: pd.DataFrame, sort_by: str = "return_12mo_pct", ascending: bool = False) -> pd.DataFrame:
    """Default sort = 12mo return descending (Section 'Stack ranking' decision)."""
    if sort_by not in table.columns:
        raise ValueError(f"Unknown sort column: {sort_by}")
    return table.sort_values(by=sort_by, ascending=ascending, na_position="last").reset_index(drop=True)
