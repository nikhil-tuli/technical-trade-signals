"""
Regression tests — this change set touched config.py (appended a new
section) and charting.py (appended a new function). Nothing in
patterns.py, support_resistance.py, indicators.py, or signal_engine.py
was edited, but these tests pin the shared modules that WERE touched or
reused, so an accidental break shows up here instead of only being
noticed later inside the Streamlit app.
"""
import types
import pandas as pd
import pytest

import config
import indicators
import patterns
import support_resistance
import signal_engine
import data_fetch
import charting


def test_all_existing_modules_still_import_cleanly():
    # Import already happened above at module load time; this test just
    # documents the intent and fails loudly with a clear name if any of
    # the imports above ever raise.
    assert True


def test_nifty_100_map_unchanged_count():
    assert len(config.NIFTY_100_MAP) == 100


def test_nifty_500_map_unchanged_count():
    assert len(config.NIFTY_500_MAP) == 500


def test_existing_config_constants_still_present():
    # Sentinel check that appending the Momentum section didn't clobber
    # or shadow any existing name.
    assert config.MIN_RR_DEFAULT == 2.0
    assert config.SR_MAX_DISTANCE_PCT_DEFAULT == 4.0
    assert config.VOLUME_MA_PERIOD_DEFAULT == 10
    assert config.TRADE_TYPE_PARAMS["short_term"]["primary_trend_ma"] == 20


def test_yf_symbol_unchanged():
    assert config.yf_symbol("INFY") == "INFY.NS"


def test_primary_trend_smoke_on_synthetic_uptrend(make_ohlcv):
    df = make_ohlcv(n_days=150, daily_drift_pct=0.3, seed=99)
    result = indicators.primary_trend(df, ma_period=20)
    assert result["trend"] in {"Up", "Down", "Sideways"}  # still returns a valid label
    assert "ma_period" in result and result["ma_period"] == 20


def test_fetch_universe_still_generic_across_any_symbol_list(monkeypatch, make_ohlcv):
    """
    data_fetch.fetch_universe() is now reused by BOTH the Signal Screener
    (Nifty 100/500) and the Momentum Screener (Nifty 500) — this test
    confirms it still works as a plain, symbol-list-agnostic function
    and wasn't accidentally special-cased for one caller.
    """
    synthetic = make_ohlcv(n_days=50, seed=100)

    def _fake_history(nse_symbol, period="18mo"):
        return synthetic, None

    monkeypatch.setattr(data_fetch, "fetch_history", _fake_history)

    results, failures = data_fetch.fetch_universe(["FAKE1", "FAKE2", "FAKE3"], period="14mo")
    assert set(results.keys()) == {"FAKE1", "FAKE2", "FAKE3"}
    assert failures == {}
    for df in results.values():
        assert list(df.columns) == list(synthetic.columns)


def test_build_signal_chart_signature_unchanged(make_ohlcv):
    """
    Doesn't re-test signal_engine's gate logic (out of scope for this
    change) — just confirms build_signal_chart() still accepts the same
    (df, sig) shape it always did, i.e. adding build_plain_chart()
    alongside it in charting.py didn't disturb the original function.
    """
    df = make_ohlcv(n_days=120, daily_drift_pct=0.2, seed=101)
    fake_sig = types.SimpleNamespace(
        symbol="FAKE", direction="bullish", entry=100.0, stop_loss=95.0, target=110.0,
        formation_date=df.index[-5], pattern="Bullish Engulfing",
        primary_trend={"ma_period": 20},
        details={
            "volume_ma_period": 10,
            "sr_validation_zone_lower": 94.0, "sr_validation_zone_upper": 96.0,
            "sr_target_zone_lower": 108.0, "sr_target_zone_upper": 112.0,
        },
    )
    fig = charting.build_signal_chart(df, fake_sig)
    assert fig is not None


def test_build_plain_chart_does_not_require_a_signal(make_ohlcv):
    df = make_ohlcv(n_days=120, daily_drift_pct=0.1, seed=102)
    fig = charting.build_plain_chart(df, "FAKE", ma_period=90)
    assert fig is not None
