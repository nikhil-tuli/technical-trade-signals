"""
Integration test — exercises the actual boundary between data_fetch.py
(fetch layer) and momentum_engine.py (ranking layer), the same call
sequence pages/1_Momentum_Screener.py performs. yfinance itself is
mocked at fetch_history() — everything downstream of that (fetch_universe's
throttling/failure-handling loop, build_momentum_table, apply_filters,
sort_table) runs for real, unmocked.
"""
import pytest

import data_fetch
import momentum_engine as me


@pytest.fixture
def three_symbol_price_data(make_ohlcv, monkeypatch):
    """One strong uptrend (liquid), one downtrend (liquid), one flat/thin
    (illiquid) — enough spread to exercise both ranking and filtering."""
    frames = {
        "STRONGUP": make_ohlcv(n_days=280, daily_drift_pct=0.35, start_price=500, volume=2_000_000, seed=201),
        "DOWNTREND": make_ohlcv(n_days=280, daily_drift_pct=-0.25, start_price=300, volume=1_500_000, seed=202),
        "THINLIQUID": make_ohlcv(n_days=280, daily_drift_pct=0.10, start_price=50, volume=5_000, seed=203),
    }

    def _fake_history(nse_symbol, period="18mo"):
        # nse_symbol arrives as the plain NSE symbol (data_fetch adds
        # the .NS suffix internally via yf_symbol before this point in
        # the real code path — fetch_history itself takes the bare symbol)
        return frames.get(nse_symbol), None

    monkeypatch.setattr(data_fetch, "fetch_history", _fake_history)
    return frames


def test_fetch_then_rank_pipeline(three_symbol_price_data, monkeypatch):
    import nse_master_data as nmd
    # Stub sector/listing lookups so this test doesn't depend on whether
    # these made-up symbols happen to exist in the real master CSV.
    monkeypatch.setattr(nmd, "get_sector", lambda sym: {"STRONGUP": "IT", "DOWNTREND": "IT", "THINLIQUID": "IT"}.get(sym))
    monkeypatch.setattr(nmd, "days_listed", lambda sym, as_of=None: 1000)

    symbols = list(three_symbol_price_data.keys())
    price_data, failures = data_fetch.fetch_universe(symbols, period="14mo")

    assert failures == {}
    assert set(price_data.keys()) == set(symbols)

    table = me.build_momentum_table(price_data, dma_period=90)
    assert len(table) == 3

    # Liquidity floor of ₹15cr (annual traded turnover, sum not average)
    # should exclude THINLIQUID (~₹7.7cr/year vs STRONGUP's ~₹46,900cr/year)
    filtered = me.apply_filters(table, liquidity_floor_cr=15.0, require_above_dma=True)
    assert "THINLIQUID" not in set(filtered["symbol"])
    # DOWNTREND should fail the price>DMA trend filter
    assert "DOWNTREND" not in set(filtered["symbol"])
    assert set(filtered["symbol"]) == {"STRONGUP"}

    ranked = me.sort_table(filtered)
    assert ranked.iloc[0]["symbol"] == "STRONGUP"


def test_partial_fetch_failure_does_not_break_ranking(three_symbol_price_data, monkeypatch):
    import nse_master_data as nmd
    monkeypatch.setattr(nmd, "get_sector", lambda sym: "IT")
    monkeypatch.setattr(nmd, "days_listed", lambda sym, as_of=None: 1000)

    # Simulate one symbol failing to fetch entirely
    def _fake_history_with_failure(nse_symbol, period="18mo"):
        if nse_symbol == "DOWNTREND":
            return None, "HTTPError: 429 rate limited"
        return three_symbol_price_data.get(nse_symbol), None

    monkeypatch.setattr(data_fetch, "fetch_history", _fake_history_with_failure)

    symbols = list(three_symbol_price_data.keys())
    price_data, failures = data_fetch.fetch_universe(symbols, period="14mo")

    assert "DOWNTREND" in failures
    assert "DOWNTREND" not in price_data
    assert len(price_data) == 2  # the other two still succeeded

    table = me.build_momentum_table(price_data, dma_period=90)
    assert set(table["symbol"]) == {"STRONGUP", "THINLIQUID"}  # ranking proceeds on what did fetch
