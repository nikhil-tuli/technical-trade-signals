"""
Config sanity checks — cheap tests that catch a typo'd constant before
it silently breaks a filter default or a UI dropdown.
"""
import config


def test_dma_default_is_in_options():
    assert config.MOMENTUM_DMA_DEFAULT in config.MOMENTUM_DMA_OPTIONS


def test_return_windows_sorted_ascending():
    assert config.MOMENTUM_RETURN_WINDOWS == sorted(config.MOMENTUM_RETURN_WINDOWS)


def test_volume_recent_shorter_than_baseline():
    assert config.MOMENTUM_VOLUME_RECENT_DAYS < config.MOMENTUM_VOLUME_BASELINE_DAYS_DEFAULT


def test_liquidity_floor_non_negative():
    assert config.MOMENTUM_LIQUIDITY_FLOOR_CR_DEFAULT >= 0


def test_fetch_period_covers_longest_return_window_plus_buffer():
    # 252 trading days ~= 12 months; fetch period must exceed that for
    # the DMA-252 warm-up to have enough history at the start of the window.
    assert "mo" in config.MOMENTUM_FETCH_PERIOD
    months = int(config.MOMENTUM_FETCH_PERIOD.replace("mo", ""))
    assert months > config.MOMENTUM_LOOKBACK_MONTHS


def test_risk_free_rate_is_a_plausible_percentage():
    # Sanity bound, not a precise check — catches a typo like 525 instead
    # of 5.25, or an accidentally negative value.
    assert 0 < config.MOMENTUM_RISK_FREE_RATE_PCT < 20


def test_liquidity_lookback_is_annual_not_30_day():
    assert config.MOMENTUM_LIQUIDITY_LOOKBACK_DAYS == 252
