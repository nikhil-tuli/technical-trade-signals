"""
End-to-end test — the full computational path a real "Generate rankings"
click runs through: fetch -> build table -> filter -> sort -> assemble
the exact display DataFrame the page renders. Uses REAL symbols and
REAL sector/listing data from nse_master_data.py (no mocking of that
layer), only the network fetch itself is synthetic.

Scope note: this is pipeline-level E2E, not browser-level E2E. It does
not click buttons in an actual rendered Streamlit page or verify pixels
— that would need Playwright/Selenium driving a live `streamlit run`
process, which isn't set up in this change set. Flagging this explicitly
rather than calling this "full E2E coverage": if browser-driven testing
becomes a priority, that's a separate, larger addition (a
tests/e2e_browser/ suite + CI runner), not something to quietly claim
coverage for here.
"""
import zlib

import pandas as pd
import pytest

import config
import data_fetch
import momentum_engine as me


REAL_SAMPLE_SYMBOLS = ["TCS", "INFY", "RELIANCE", "HDFCBANK", "ITC"]


def _stable_seed(text: str) -> int:
    """Deterministic seed from a string. Python's built-in hash() is
    randomized per-process for str (PEP 456 hash randomization) unless
    PYTHONHASHSEED is fixed — using it here would make this test flaky
    run-to-run, exactly the kind of thing a regression suite shouldn't do."""
    return zlib.crc32(text.encode()) % 1000


def test_five_real_symbols_full_pipeline(make_ohlcv, monkeypatch):
    for sym in REAL_SAMPLE_SYMBOLS:
        assert sym in config.NIFTY_500_MAP, f"{sym} expected in Nifty 500 universe for this test"

    # Give each symbol a distinct, controlled trend so filter/sort
    # behavior is verifiable, not just "didn't crash".
    drifts = {"TCS": 0.4, "INFY": 0.3, "RELIANCE": 0.05, "HDFCBANK": -0.2, "ITC": 0.15}
    synthetic_frames = {
        sym: make_ohlcv(n_days=300, daily_drift_pct=drifts[sym], start_price=1000,
                         volume=3_000_000, seed=_stable_seed(sym))
        for sym in REAL_SAMPLE_SYMBOLS
    }

    def _fake_history(nse_symbol, period="18mo"):
        return synthetic_frames.get(nse_symbol), None

    monkeypatch.setattr(data_fetch, "fetch_history", _fake_history)

    # --- Step 1: fetch (real fetch_universe, real throttle loop) ---
    price_data, failures = data_fetch.fetch_universe(REAL_SAMPLE_SYMBOLS, period=config.MOMENTUM_FETCH_PERIOD)
    assert failures == {}
    assert set(price_data.keys()) == set(REAL_SAMPLE_SYMBOLS)

    # --- Step 2: build table (real sector/listing lookups from the
    # shipped data/nifty500_master.csv, not mocked) ---
    table = me.build_momentum_table(price_data, dma_period=config.MOMENTUM_DMA_DEFAULT, exclude_last_month=False)
    assert len(table) == 5
    # Real sector data should be populated (not None) for every real symbol
    assert table["sector"].notna().all()
    assert table["days_listed"].notna().all()
    assert table["listing_date"].notna().all()
    assert table["current_price"].notna().all()
    assert table["week_52_high"].notna().all()
    assert table["dma_value"].notna().all()  # 300 days of synthetic data comfortably covers a 90-day DMA
    # volatility_pct column removed (redundant with Sharpe ratio) — see momentum_engine.py
    # Relative-momentum columns present and internally consistent
    assert table["sector_avg_return_12mo_pct"].notna().all()
    for _, row in table.iterrows():
        assert row["relative_to_sector_return_12mo_pct"] == pytest.approx(
            row["return_12mo_pct"] - row["sector_avg_return_12mo_pct"], abs=0.01
        )

    # --- Step 3: filter, using actual UI defaults from config.py ---
    filtered = me.apply_filters(
        table,
        min_listing_months=config.MOMENTUM_MIN_LISTING_MONTHS_DEFAULT,
        liquidity_floor_cr=config.MOMENTUM_LIQUIDITY_FLOOR_CR_DEFAULT,
        require_above_dma=True,
    )
    # HDFCBANK has negative drift -> should fail the price>DMA filter
    assert "HDFCBANK" not in set(filtered["symbol"])
    # All 5 are long-listed, large-cap, high-volume names -> liquidity/listing filters shouldn't remove them
    assert set(filtered["symbol"]) == {"TCS", "INFY", "RELIANCE", "ITC"}

    # --- Step 4: sort (default = 12mo return, descending) ---
    ranked = me.sort_table(filtered, sort_by="return_12mo_pct")
    returns = ranked["return_12mo_pct"].tolist()
    assert returns == sorted(returns, reverse=True)
    # TCS had the strongest drift -> should rank first
    assert ranked.iloc[0]["symbol"] == "TCS"

    # --- Step 5: assemble the display DataFrame exactly as the page does ---
    display_cols = [
        "symbol", "sector", "current_price", "week_52_high", "dma_value",
        "return_12mo_abs", "return_12mo_pct",
        "sector_avg_return_12mo_pct", "relative_to_sector_return_12mo_pct",
    ] + [f"return_{w}d_pct" for w in config.MOMENTUM_RETURN_WINDOWS] + [
        "sharpe_ratio", "hit_rate_pct",
        "volume_participation_pct", "annual_traded_turnover_cr", "listing_date",
    ]
    display_df = ranked[display_cols].rename(columns={
        "symbol": "Stock", "sector": "Sector",
        "current_price": "Last closed price ₹", "week_52_high": "52-week high ₹",
        "dma_value": f"{config.MOMENTUM_DMA_DEFAULT}-day DMA ₹",
        "sector_avg_return_12mo_pct": "Sector avg 12mo returns %",
        "relative_to_sector_return_12mo_pct": "Vs sector 12mo returns (pts)",
        "return_12mo_abs": "12mo returns ₹", "return_12mo_pct": "12mo returns %",
        **{f"return_{w}d_pct": f"{w}d returns %" for w in config.MOMENTUM_RETURN_WINDOWS},
        "sharpe_ratio": "Sharpe ratio", "hit_rate_pct": "Hit rate %",
        "volume_participation_pct": "Relative Volume %", "annual_traded_turnover_cr": "Annual traded turnover ₹cr",
        "listing_date": "Listing date",
    })
    assert list(display_df.columns) == [
        "Stock", "Sector", "Last closed price ₹", "52-week high ₹", f"{config.MOMENTUM_DMA_DEFAULT}-day DMA ₹",
        "12mo returns ₹", "12mo returns %", "Sector avg 12mo returns %", "Vs sector 12mo returns (pts)",
        "30d returns %", "60d returns %", "90d returns %", "180d returns %",
        "Sharpe ratio", "Hit rate %", "Relative Volume %", "Annual traded turnover ₹cr",
        "Listing date",
    ]
    assert len(display_df) == 4
    assert display_df.iloc[0]["Stock"] == "TCS"
    assert display_df.iloc[0]["Last closed price ₹"] > 0
    assert display_df.iloc[0]["52-week high ₹"] >= display_df.iloc[0]["Last closed price ₹"]
    assert display_df.iloc[0]["Listing date"] is not None


def test_no_matches_produces_empty_not_broken_table(make_ohlcv, monkeypatch):
    """An unreasonably high liquidity floor should yield an empty,
    well-formed result — not an exception — matching the page's
    'no stocks matched' branch."""
    synthetic = make_ohlcv(n_days=300, daily_drift_pct=0.2, start_price=100, volume=1000, seed=999)

    def _fake_history(nse_symbol, period="18mo"):
        return synthetic, None

    monkeypatch.setattr(data_fetch, "fetch_history", _fake_history)
    price_data, _ = data_fetch.fetch_universe(["TCS"], period=config.MOMENTUM_FETCH_PERIOD)
    table = me.build_momentum_table(price_data, dma_period=config.MOMENTUM_DMA_DEFAULT)
    filtered = me.apply_filters(table, liquidity_floor_cr=999_999.0, require_above_dma=False)
    assert filtered.empty
    assert list(filtered.columns) == list(table.columns)  # shape preserved even when empty


REAL_MULTI_SECTOR_SYMBOLS = ["TCS", "INFY", "WIPRO", "HDFCBANK", "ICICIBANK", "SBIN"]


def test_sector_view_full_pipeline_real_symbols_multiple_sectors(make_ohlcv, monkeypatch):
    """
    Mirrors test_five_real_symbols_full_pipeline above, but for the
    Sector View path: fetch -> build per-stock table -> aggregate to
    sectors -> filter -> sort -> assemble the exact display DataFrame
    the Sector View tab renders. Real symbols spanning 2 real sectors
    (IT, Financial Services), so the aggregation and "vs universe"
    math are checked against real NSE sector data, not a stub.
    """
    for sym in REAL_MULTI_SECTOR_SYMBOLS:
        assert sym in config.NIFTY_500_MAP

    drifts = {"TCS": 0.4, "INFY": 0.3, "WIPRO": 0.1, "HDFCBANK": -0.1, "ICICIBANK": 0.05, "SBIN": 0.15}
    synthetic_frames = {
        sym: make_ohlcv(n_days=300, daily_drift_pct=drifts[sym], start_price=500,
                         volume=2_000_000, seed=_stable_seed(sym))
        for sym in REAL_MULTI_SECTOR_SYMBOLS
    }

    def _fake_history(nse_symbol, period="18mo"):
        return synthetic_frames.get(nse_symbol), None

    monkeypatch.setattr(data_fetch, "fetch_history", _fake_history)

    price_data, failures = data_fetch.fetch_universe(REAL_MULTI_SECTOR_SYMBOLS, period=config.MOMENTUM_FETCH_PERIOD)
    assert failures == {}

    table = me.build_momentum_table(price_data, dma_period=config.MOMENTUM_DMA_DEFAULT, exclude_last_month=False)
    sector_table = me.build_sector_table(table)

    # Real NSE data: TCS/INFY/WIPRO -> Information Technology, HDFCBANK/ICICIBANK/SBIN -> Financial Services
    assert set(sector_table["sector"]) == {"Information Technology", "Financial Services"}

    it_row = sector_table[sector_table["sector"] == "Information Technology"].iloc[0]
    fs_row = sector_table[sector_table["sector"] == "Financial Services"].iloc[0]
    assert it_row["num_stocks"] == 3
    assert fs_row["num_stocks"] == 3
    # IT has the strongest drifts -> should have the higher average 12mo return
    assert it_row["avg_return_12mo_pct"] > fs_row["avg_return_12mo_pct"]
    # vs-universe deltas should be internally consistent with each other
    universe_avg = table["return_12mo_pct"].mean()
    assert it_row["vs_universe_return_12mo_pct"] == pytest.approx(it_row["avg_return_12mo_pct"] - universe_avg, abs=0.01)

    # --- filter + sort, same calls the page makes ---
    filtered = me.apply_sector_filters(sector_table, min_avg_return_12mo_pct=0.0)
    assert set(filtered["sector"]) == {"Information Technology", "Financial Services"}  # both positive-average here
    ranked = me.sort_table(filtered, sort_by="avg_return_12mo_pct")
    assert ranked.iloc[0]["sector"] == "Information Technology"

    # --- assemble display frame, same shape the page builds ---
    def _fmt_count_pct(count, pct):
        return f"{int(count)} ({pct:.0f}%)" if pct == pct else "—"  # pct==pct is a NaN-safe check

    display = pd.DataFrame({
        "Sector": ranked["sector"],
        "Avg 12mo returns %": ranked["avg_return_12mo_pct"],
        "Stocks up (12mo)": [
            _fmt_count_pct(c, p) for c, p in zip(ranked["stocks_up_12mo_count"], ranked["stocks_up_12mo_pct"])
        ],
    })
    assert display.iloc[0]["Sector"] == "Information Technology"
    assert "(" in display.iloc[0]["Stocks up (12mo)"]  # "N (P%)" format, not raw separate numbers
