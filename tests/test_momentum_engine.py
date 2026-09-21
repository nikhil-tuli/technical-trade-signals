"""
Unit tests — momentum_engine.py pure functions, synthetic data only.
"""
import pandas as pd
import pytest

import momentum_engine as me


class TestNDayReturn:
    def test_known_return(self, make_ohlcv):
        df = make_ohlcv(n_days=100, daily_drift_pct=0.0, seed=1)
        # Force an exact, known 10-day return by hand-editing two closes
        df.loc[df.index[-11], "Close"] = 100.0
        df.loc[df.index[-1], "Close"] = 110.0
        assert me.n_day_return_pct(df, 10) == pytest.approx(10.0, abs=0.01)

    def test_insufficient_history_returns_none(self, make_ohlcv):
        df = make_ohlcv(n_days=5, seed=1)
        assert me.n_day_return_pct(df, 30) is None

    def test_zero_start_price_returns_none(self, make_ohlcv):
        df = make_ohlcv(n_days=20, seed=1)
        df.loc[df.index[-21] if len(df) > 20 else df.index[0], "Close"] = 0.0
        # rebuild a clean minimal case instead of relying on off-by-one above
        df2 = make_ohlcv(n_days=15, seed=1)
        df2.iloc[0, df2.columns.get_loc("Close")] = 0.0
        assert me.n_day_return_pct(df2, 14) is None


class TestLookbackReturn:
    def test_exclude_last_month_changes_result(self, make_ohlcv):
        df = make_ohlcv(n_days=300, daily_drift_pct=0.3, seed=2)
        abs_incl, pct_incl = me.lookback_return_pct(df, months=12, exclude_last_month=False)
        abs_excl, pct_excl = me.lookback_return_pct(df, months=12, exclude_last_month=True)
        assert pct_incl is not None and pct_excl is not None
        assert pct_incl != pct_excl  # different windows must give different numbers

    def test_too_short_returns_none_tuple(self, make_ohlcv):
        df = make_ohlcv(n_days=10, seed=3)
        assert me.lookback_return_pct(df, months=12) == (None, None)


class TestSharpeRatio:
    def test_flat_series_returns_none(self, make_ohlcv):
        df = make_ohlcv(n_days=280, daily_drift_pct=0.0, seed=4)
        df["Close"] = 100.0  # perfectly flat -> zero volatility
        assert me.sharpe_ratio(df) is None

    def test_smooth_uptrend_well_above_risk_free_rate_is_positive(self, make_ohlcv):
        df = make_ohlcv(n_days=280, daily_drift_pct=0.2, seed=5)
        ratio = me.sharpe_ratio(df)
        assert ratio is not None and ratio > 0

    def test_risk_free_rate_is_actually_subtracted(self, make_ohlcv):
        # Same series, two different assumed risk-free rates -> a higher
        # risk-free rate must produce a LOWER Sharpe ratio. This is the
        # whole point of the change (Ret/vol implicitly assumed rf=0).
        df = make_ohlcv(n_days=280, daily_drift_pct=0.2, seed=5)
        ratio_low_rf = me.sharpe_ratio(df, risk_free_rate_pct=1.0)
        ratio_high_rf = me.sharpe_ratio(df, risk_free_rate_pct=10.0)
        assert ratio_low_rf is not None and ratio_high_rf is not None
        assert ratio_high_rf < ratio_low_rf

    def test_return_exactly_at_risk_free_rate_gives_zero_sharpe(self, make_ohlcv):
        # Construct a series with a known ~12mo return, then set the
        # risk-free rate to match it -> Sharpe should be ~0.
        df = make_ohlcv(n_days=280, daily_drift_pct=0.1, seed=6)
        _, pct_return = me.lookback_return_pct(df)
        assert pct_return is not None
        ratio = me.sharpe_ratio(df, risk_free_rate_pct=pct_return)
        assert ratio == pytest.approx(0.0, abs=0.01)

    def test_uses_config_default_risk_free_rate_when_not_specified(self, make_ohlcv):
        import config
        df = make_ohlcv(n_days=280, daily_drift_pct=0.2, seed=5)
        default_call = me.sharpe_ratio(df)
        explicit_call = me.sharpe_ratio(df, risk_free_rate_pct=config.MOMENTUM_RISK_FREE_RATE_PCT)
        assert default_call == explicit_call

    def test_denominator_matches_manual_annualized_std_dev(self, make_ohlcv):
        # Verifies the annualization math directly against a manually
        # computed daily-returns std dev, WITHOUT depending on the
        # disabled volatility_pct() — uses the still-live _daily_returns()
        # internal helper instead, so this stays valid regardless of
        # whether volatility_pct is ever re-enabled.
        import math
        df = make_ohlcv(n_days=280, daily_drift_pct=0.2, seed=15)
        daily_returns = me._daily_returns(df)
        assert not daily_returns.empty
        manual_annualized_vol_pct = daily_returns.std() * 100 * math.sqrt(me.TRADING_DAYS_PER_YEAR)
        _, pct_return = me.lookback_return_pct(df)
        ratio = me.sharpe_ratio(df, risk_free_rate_pct=5.25)
        assert ratio == pytest.approx((pct_return - 5.25) / manual_annualized_vol_pct, rel=0.01)


class TestHitRate:
    def test_known_hit_rate(self):
        # months=1 -> a 21-trading-day window needs >=~19 days of
        # coverage (MIN_WINDOW_COVERAGE guard) to be considered valid,
        # so this builds a full 22-close window (21 daily-return
        # observations) rather than a handful of days. Expected hit
        # rate is derived from the deltas themselves, not hardcoded, so
        # this test can't silently drift from what the deltas actually mean.
        deltas = [1, 1, 1, -1, 1, 1, -1, 1, 1, 1, -1, 1, 1, 1, -1, 1, 1, 1, -1, 1, 1]
        assert len(deltas) == 21
        closes = [100]
        for d in deltas:
            closes.append(closes[-1] + d)
        df = pd.DataFrame({"Close": closes}, index=pd.bdate_range("2024-01-01", periods=len(closes)))
        df["Open"] = df["High"] = df["Low"] = df["Close"]
        df["Volume"] = 1_000_000
        rate = me.hit_rate_pct(df, months=1)
        expected = round((sum(1 for d in deltas if d > 0) / len(deltas)) * 100, 1)
        assert rate == pytest.approx(expected, abs=0.1)

    def test_insufficient_data_returns_none(self, make_ohlcv):
        df = make_ohlcv(n_days=2, seed=6)
        assert me.hit_rate_pct(df) is None


class TestPriceAboveDma:
    def test_uptrend_is_above(self, make_ohlcv):
        df = make_ohlcv(n_days=150, daily_drift_pct=0.3, seed=7)
        assert me.price_above_dma(df, 90) is True

    def test_downtrend_is_below(self, make_ohlcv):
        df = make_ohlcv(n_days=150, daily_drift_pct=-0.3, seed=8)
        assert me.price_above_dma(df, 90) is False

    def test_insufficient_history_returns_none(self, make_ohlcv):
        df = make_ohlcv(n_days=10, seed=9)
        assert me.price_above_dma(df, 90) is None


class TestCurrentPrice:
    def test_returns_latest_close(self):
        df = pd.DataFrame(
            {"Close": [100.0, 105.0, 110.5], "Open": [100, 105, 110], "High": [101, 106, 111],
             "Low": [99, 104, 109], "Volume": [1000, 1000, 1000]},
            index=pd.bdate_range("2024-01-01", periods=3),
        )
        assert me.current_price(df) == 110.5

    def test_empty_df_returns_none(self):
        assert me.current_price(pd.DataFrame(columns=["Close"])) is None


class TestDmaValue:
    def test_known_average(self):
        # 10 closes, all distinct -> 10-day DMA is their mean
        closes = [100, 102, 101, 103, 104, 102, 105, 106, 104, 107]
        df = pd.DataFrame(
            {"Close": closes, "Open": closes, "High": closes, "Low": closes, "Volume": [1000] * 10},
            index=pd.bdate_range("2024-01-01", periods=10),
        )
        expected = round(sum(closes) / len(closes), 2)
        assert me.dma_value(df, 10) == pytest.approx(expected, abs=0.01)

    def test_insufficient_history_returns_none(self, make_ohlcv):
        df = make_ohlcv(n_days=10, seed=14)
        assert me.dma_value(df, 90) is None


class TestVolumeParticipation:
    def test_spike_shows_above_100(self, make_ohlcv):
        df = make_ohlcv(n_days=100, seed=10, volume_spike_last_n=10)
        pct = me.volume_participation_pct(df, recent_days=10, baseline_days=50)
        assert pct is not None and pct > 100

    def test_flat_volume_is_100(self, make_ohlcv):
        df = make_ohlcv(n_days=100, seed=11)  # no spike -> constant volume
        pct = me.volume_participation_pct(df, recent_days=10, baseline_days=50)
        assert pct == pytest.approx(100.0, abs=0.5)


class TestAnnualTradedTurnover:
    def test_known_turnover_is_a_sum_not_an_average(self):
        df = pd.DataFrame({
            "Close": [100.0] * 30,
            "Volume": [1_000_000.0] * 30,
            "Open": [100.0] * 30, "High": [100.0] * 30, "Low": [100.0] * 30,
        }, index=pd.bdate_range("2024-01-01", periods=30))
        # Each day: 100 x 1,000,000 = 10,00,00,000 = 10 crore.
        # SUM over 30 days (not average) -> 300 crore. This is the key
        # behavior change from the old avg_daily_turnover_cr (which
        # would have returned 10.0, the per-day average).
        assert me.annual_traded_turnover_cr(df, lookback_days=30) == pytest.approx(300.0, abs=0.01)

    def test_default_lookback_is_252_trading_days(self):
        import config
        assert config.MOMENTUM_LIQUIDITY_LOOKBACK_DAYS == 252


# DISABLED — matches momentum_engine.py's commented-out volatility_pct().
# Commented out rather than deleted so re-enabling is a mirror-image
# uncomment on both sides if the function ever comes back.
#
# class TestVolatilityPct:
#     def test_matches_sharpe_ratio_denominator(self, make_ohlcv):
#         import math
#         df = make_ohlcv(n_days=280, daily_drift_pct=0.2, seed=15)
#         vol = me.volatility_pct(df)
#         ratio = me.sharpe_ratio(df, risk_free_rate_pct=5.25)
#         _, pct_return = me.lookback_return_pct(df)
#         assert vol is not None and ratio is not None and pct_return is not None
#         annualized_vol = vol * math.sqrt(me.TRADING_DAYS_PER_YEAR)
#         assert ratio == pytest.approx((pct_return - 5.25) / annualized_vol, rel=0.01)
#
#     def test_flat_series_returns_zero_not_none(self, make_ohlcv):
#         df = make_ohlcv(n_days=280, seed=16)
#         df["Close"] = 100.0
#         assert me.volatility_pct(df) == pytest.approx(0.0)
#
#     def test_insufficient_data_returns_none(self, make_ohlcv):
#         df = make_ohlcv(n_days=5, seed=17)
#         assert me.volatility_pct(df) is None


class TestWeek52High:
    def test_known_high(self):
        closes = [100, 150, 120, 90, 110]
        df = pd.DataFrame({
            "Close": closes, "Open": closes, "Low": closes,
            "High": [c + 5 for c in closes],  # High always 5 above Close for this fixture
            "Volume": [1000] * 5,
        }, index=pd.bdate_range("2024-01-01", periods=5))
        assert me.week_52_high(df) == 155.0  # 150 + 5

    def test_uses_available_history_when_under_252_days(self, make_ohlcv):
        df = make_ohlcv(n_days=30, seed=18)
        result = me.week_52_high(df)
        assert result is not None
        assert result == pytest.approx(df["High"].max(), abs=0.01)

    def test_empty_df_returns_none(self):
        assert me.week_52_high(pd.DataFrame(columns=["High"])) is None


class TestPricePoints:
    def test_today_and_windows_match_known_closes(self):
        # 253 rows: enough for today + all of MOMENTUM_RETURN_WINDOWS (up
        # to 180d) + the 252-day 12mo window (window_days+1 = 253).
        n = 253
        closes = list(range(100, 100 + n))  # 100, 101, ..., 100+n-1 — strictly increasing, easy to check
        df = pd.DataFrame({
            "Close": closes, "Open": closes, "High": closes, "Low": closes, "Volume": [1000] * n,
        }, index=pd.bdate_range("2020-01-01", periods=n))

        points = me.price_points(df)

        assert points["today"][0] == closes[-1]
        assert points["today"][1] == df.index[-1]
        for w in me.MOMENTUM_RETURN_WINDOWS:
            price, date = points[w]
            assert price == closes[-w - 1]
            assert date == df.index[-w - 1]
        # 12mo window uses the same window_days+1 = 253 slice as
        # lookback_return_pct -> first element of that slice, which for
        # a full 253-row df is the very first row.
        price_12mo, date_12mo = points["12mo"]
        assert price_12mo == closes[0]
        assert date_12mo == df.index[0]

    def test_insufficient_history_gives_none_pairs_not_missing_keys(self, make_ohlcv):
        df = make_ohlcv(n_days=10, seed=50)
        points = me.price_points(df)
        assert points["today"][0] is not None  # always available if df non-empty
        assert points[180] == (None, None)  # 10 days can't reach a 180-day-ago close
        assert points["12mo"] == (None, None)

    def test_empty_df_returns_empty_dict(self):
        assert me.price_points(pd.DataFrame(columns=["Close"])) == {}

    def test_exclude_last_month_shifts_the_12mo_point_only(self, make_ohlcv):
        df = make_ohlcv(n_days=300, daily_drift_pct=0.1, seed=51)
        points_incl = me.price_points(df, exclude_last_month=False)
        points_excl = me.price_points(df, exclude_last_month=True)
        # today and the fixed N-day windows are unaffected by the toggle
        assert points_incl["today"] == points_excl["today"]
        assert points_incl[30] == points_excl[30]
        # the 12mo point shifts (different date/price) when the toggle is on
        assert points_incl["12mo"] != points_excl["12mo"]


class TestAddRelativeMomentum:
    def test_sector_average_and_relative_computed_correctly(self):
        table = pd.DataFrame([
            {"symbol": "A", "sector": "IT", "return_12mo_pct": 20.0},
            {"symbol": "B", "sector": "IT", "return_12mo_pct": 40.0},
            {"symbol": "C", "sector": "Financial Services", "return_12mo_pct": 10.0},
        ])
        result = me.add_relative_momentum(table)
        it_avg = (20.0 + 40.0) / 2
        assert result.loc[result["symbol"] == "A", "sector_avg_return_12mo_pct"].iloc[0] == pytest.approx(it_avg)
        assert result.loc[result["symbol"] == "A", "relative_to_sector_return_12mo_pct"].iloc[0] == pytest.approx(20.0 - it_avg)
        assert result.loc[result["symbol"] == "B", "relative_to_sector_return_12mo_pct"].iloc[0] == pytest.approx(40.0 - it_avg)
        # Only stock in its sector -> relative to itself -> 0
        assert result.loc[result["symbol"] == "C", "relative_to_sector_return_12mo_pct"].iloc[0] == pytest.approx(0.0)

    def test_missing_sector_produces_nan(self):
        table = pd.DataFrame([{"symbol": "X", "sector": None, "return_12mo_pct": 15.0}])
        result = me.add_relative_momentum(table)
        assert pd.isna(result.loc[0, "sector_avg_return_12mo_pct"])
        assert pd.isna(result.loc[0, "relative_to_sector_return_12mo_pct"])


class TestApplyFilters:
    def _sample_table(self):
        return pd.DataFrame([
            {"symbol": "A", "sector": "IT", "days_listed": 1000, "annual_traded_turnover_cr": 20.0,
             "price_above_dma": True, "return_12mo_pct": 50.0, "current_price": 500.0, "volatility_pct": 2.0,
             "sharpe_ratio": 1.5},
            {"symbol": "B", "sector": "Financial Services", "days_listed": 40, "annual_traded_turnover_cr": 5.0,
             "price_above_dma": True, "return_12mo_pct": 10.0, "current_price": 50.0, "volatility_pct": 3.5,
             "sharpe_ratio": -0.5},
            {"symbol": "C", "sector": "IT", "days_listed": 2000, "annual_traded_turnover_cr": 30.0,
             "price_above_dma": False, "return_12mo_pct": 90.0, "current_price": 1200.0, "volatility_pct": 4.0,
             "sharpe_ratio": 2.0},
            {"symbol": "D", "sector": "IT", "days_listed": 500, "annual_traded_turnover_cr": None,
             "price_above_dma": True, "return_12mo_pct": 5.0, "current_price": None, "volatility_pct": None,
             "sharpe_ratio": None},
        ])

    def test_sector_filter(self):
        out = me.apply_filters(self._sample_table(), sector="IT", require_above_dma=False)
        assert set(out["symbol"]) == {"A", "C", "D"}

    def test_listing_period_filter(self):
        out = me.apply_filters(self._sample_table(), min_listing_months=6, require_above_dma=False)
        assert "B" not in set(out["symbol"])  # 40 days < 6 months

    def test_liquidity_filter_excludes_none_and_below_floor(self):
        out = me.apply_filters(self._sample_table(), liquidity_floor_cr=15.0, require_above_dma=False)
        assert set(out["symbol"]) == {"A", "C"}  # B below floor, D is None -> excluded

    def test_dma_filter_excludes_false(self):
        out = me.apply_filters(self._sample_table(), require_above_dma=True)
        assert "C" not in set(out["symbol"])

    def test_min_price_filter_excludes_below_and_none(self):
        out = me.apply_filters(self._sample_table(), min_price=100.0, require_above_dma=False)
        assert set(out["symbol"]) == {"A", "C"}  # B below 100, D is None -> excluded

    def test_min_price_none_means_no_filter(self):
        out = me.apply_filters(self._sample_table(), min_price=None, require_above_dma=False)
        assert set(out["symbol"]) == {"A", "B", "C", "D"}

    # DISABLED — max_volatility_pct is now a no-op in apply_filters
    # (see momentum_engine.py). Commented out to match, not deleted.
    # def test_max_volatility_filter_excludes_above_and_none(self):
    #     out = me.apply_filters(self._sample_table(), max_volatility_pct=3.0, require_above_dma=False)
    #     assert set(out["symbol"]) == {"A"}  # B (3.5) and C (4.0) above 3.0, D is None -> all excluded

    def test_max_volatility_pct_param_is_a_harmless_no_op(self):
        # Passing it should not raise and should not change results —
        # confirms the "commented out, not removed from signature" state.
        with_param = me.apply_filters(self._sample_table(), max_volatility_pct=3.0, require_above_dma=False)
        without_param = me.apply_filters(self._sample_table(), require_above_dma=False)
        assert set(with_param["symbol"]) == set(without_param["symbol"])

    def test_min_sharpe_ratio_filter_excludes_below_and_none(self):
        out = me.apply_filters(self._sample_table(), min_sharpe_ratio=1.0, require_above_dma=False)
        assert set(out["symbol"]) == {"A", "C"}  # B (-0.5) below 1.0, D is None -> excluded

    def test_min_sharpe_ratio_allows_negative_threshold(self):
        # A negative threshold should still work (excludes only worse-than-threshold, keeps B)
        out = me.apply_filters(self._sample_table(), min_sharpe_ratio=-1.0, require_above_dma=False)
        assert set(out["symbol"]) == {"A", "B", "C"}  # D still excluded (None)

    def test_min_sharpe_ratio_none_means_no_filter(self):
        out = me.apply_filters(self._sample_table(), min_sharpe_ratio=None, require_above_dma=False)
        assert set(out["symbol"]) == {"A", "B", "C", "D"}

    def test_combined_filters(self):
        out = me.apply_filters(
            self._sample_table(), sector="IT", liquidity_floor_cr=15.0, require_above_dma=True,
        )
        assert set(out["symbol"]) == {"A"}


class TestBuildSectorTable:
    def _sample_table(self):
        return pd.DataFrame([
            {"symbol": "A", "sector": "IT", "return_12mo_pct": 20.0, "return_30d_pct": 2.0,
             "return_60d_pct": 3.0, "return_90d_pct": 4.0, "return_180d_pct": 5.0,
             "price_above_dma": True, "sharpe_ratio": 1.0, "annual_traded_turnover_cr": 100.0,
             "volume_participation_pct": 110.0},
            {"symbol": "B", "sector": "IT", "return_12mo_pct": 40.0, "return_30d_pct": 1.0,
             "return_60d_pct": 2.0, "return_90d_pct": 3.0, "return_180d_pct": 4.0,
             "price_above_dma": False, "sharpe_ratio": 2.0, "annual_traded_turnover_cr": 200.0,
             "volume_participation_pct": 90.0},
            {"symbol": "C", "sector": "Financial Services", "return_12mo_pct": -10.0,
             "return_30d_pct": None, "return_60d_pct": None, "return_90d_pct": None,
             "return_180d_pct": None, "price_above_dma": None, "sharpe_ratio": None,
             "annual_traded_turnover_cr": None, "volume_participation_pct": None},
            {"symbol": "D", "sector": None, "return_12mo_pct": 100.0, "return_30d_pct": 10.0,
             "return_60d_pct": 10.0, "return_90d_pct": 10.0, "return_180d_pct": 10.0,
             "price_above_dma": True, "sharpe_ratio": 5.0, "annual_traded_turnover_cr": 500.0,
             "volume_participation_pct": 200.0},
        ])

    def test_none_sector_excluded_from_rows_but_counted_in_universe_average(self):
        sec = me.build_sector_table(self._sample_table())
        assert set(sec["sector"]) == {"IT", "Financial Services"}  # D (sector=None) has no row
        # Universe avg across ALL 4 rows (including D) = (20+40-10+100)/4 = 37.5
        it_row = sec[sec["sector"] == "IT"].iloc[0]
        assert it_row["avg_return_12mo_pct"] == pytest.approx(30.0)  # (20+40)/2
        assert it_row["vs_universe_return_12mo_pct"] == pytest.approx(30.0 - 37.5)

    def test_median_differs_from_mean_with_skewed_data(self):
        table = pd.DataFrame([
            {"symbol": "A", "sector": "IT", "return_12mo_pct": 5.0, "return_30d_pct": None,
             "return_60d_pct": None, "return_90d_pct": None, "return_180d_pct": None,
             "price_above_dma": None, "sharpe_ratio": None, "annual_traded_turnover_cr": None,
             "volume_participation_pct": None},
            {"symbol": "B", "sector": "IT", "return_12mo_pct": 6.0, "return_30d_pct": None,
             "return_60d_pct": None, "return_90d_pct": None, "return_180d_pct": None,
             "price_above_dma": None, "sharpe_ratio": None, "annual_traded_turnover_cr": None,
             "volume_participation_pct": None},
            {"symbol": "C", "sector": "IT", "return_12mo_pct": 400.0, "return_30d_pct": None,
             "return_60d_pct": None, "return_90d_pct": None, "return_180d_pct": None,
             "price_above_dma": None, "sharpe_ratio": None, "annual_traded_turnover_cr": None,
             "volume_participation_pct": None},
        ])
        sec = me.build_sector_table(table)
        row = sec.iloc[0]
        assert row["avg_return_12mo_pct"] == pytest.approx((5 + 6 + 400) / 3)  # skewed by the 400
        assert row["med_return_12mo_pct"] == pytest.approx(6.0)  # unaffected by the outlier

    def test_breadth_denominator_excludes_missing_values_not_total_stock_count(self):
        # Financial Services has 1 stock with entirely None trend/volume
        # metrics -> the DMA breadth denominator should be 0/None, not
        # "0 out of 1" silently counted as 0%.
        sec = me.build_sector_table(self._sample_table())
        fs_row = sec[sec["sector"] == "Financial Services"].iloc[0]
        assert pd.isna(fs_row["stocks_above_dma_pct"])  # price_above_dma is None -> no valid denominator
        # return_12mo_pct IS populated for this stock (-10.0), so the "up"
        # breadth denominator is valid (1 stock, not up since -10 < 0).
        assert fs_row["stocks_up_12mo_pct"] == 0.0

    def test_num_stocks_reflects_full_sector_membership(self):
        sec = me.build_sector_table(self._sample_table())
        it_row = sec[sec["sector"] == "IT"].iloc[0]
        assert it_row["num_stocks"] == 2

    def test_empty_table_returns_empty_dataframe(self):
        assert me.build_sector_table(pd.DataFrame()).empty

    def test_all_none_sector_returns_empty_dataframe(self):
        table = pd.DataFrame([{"symbol": "X", "sector": None, "return_12mo_pct": 10.0}])
        assert me.build_sector_table(table).empty


class TestApplySectorFilters:
    def _sample_sector_table(self):
        return pd.DataFrame([
            {"sector": "IT", "avg_return_12mo_pct": 30.0, "avg_sharpe_ratio": 1.5},
            {"sector": "Financial Services", "avg_return_12mo_pct": -10.0, "avg_sharpe_ratio": None},
            {"sector": "Healthcare", "avg_return_12mo_pct": 15.0, "avg_sharpe_ratio": 0.8},
        ])

    def test_sector_filter(self):
        out = me.apply_sector_filters(self._sample_sector_table(), sector="IT")
        assert set(out["sector"]) == {"IT"}

    def test_all_sectors_means_no_filter(self):
        out = me.apply_sector_filters(self._sample_sector_table(), sector="All sectors")
        assert len(out) == 3

    def test_min_avg_return_excludes_below_threshold(self):
        out = me.apply_sector_filters(self._sample_sector_table(), min_avg_return_12mo_pct=0.0)
        assert set(out["sector"]) == {"IT", "Healthcare"}

    def test_min_avg_sharpe_excludes_below_and_none(self):
        out = me.apply_sector_filters(self._sample_sector_table(), min_avg_sharpe_ratio=1.0)
        assert set(out["sector"]) == {"IT"}  # Healthcare (0.8) below, Financial Services (None) excluded

    def test_none_thresholds_mean_no_filter(self):
        out = me.apply_sector_filters(
            self._sample_sector_table(), min_avg_return_12mo_pct=None, min_avg_sharpe_ratio=None,
        )
        assert len(out) == 3


class TestSortTable:
    def test_default_sort_descending(self):
        df = pd.DataFrame([
            {"symbol": "A", "return_12mo_pct": 10.0},
            {"symbol": "B", "return_12mo_pct": 30.0},
            {"symbol": "C", "return_12mo_pct": 20.0},
        ])
        out = me.sort_table(df)
        assert list(out["symbol"]) == ["B", "C", "A"]

    def test_none_values_sorted_last(self):
        df = pd.DataFrame([
            {"symbol": "A", "return_12mo_pct": 10.0},
            {"symbol": "B", "return_12mo_pct": None},
        ])
        out = me.sort_table(df)
        assert list(out["symbol"]) == ["A", "B"]

    def test_unknown_column_raises(self):
        df = pd.DataFrame([{"symbol": "A", "return_12mo_pct": 10.0}])
        with pytest.raises(ValueError):
            me.sort_table(df, sort_by="not_a_real_column")


class TestBuildMomentumTable:
    def test_skips_empty_and_none_frames(self, make_ohlcv):
        good_df = make_ohlcv(n_days=280, daily_drift_pct=0.2, seed=12)
        price_data = {"GOODSYM": good_df, "EMPTYSYM": pd.DataFrame(), "NONESYM": None}
        table = me.build_momentum_table(price_data, dma_period=90)
        assert list(table["symbol"]) == ["GOODSYM"]

    def test_row_has_expected_columns(self, make_ohlcv):
        df = make_ohlcv(n_days=280, daily_drift_pct=0.1, seed=13)
        table = me.build_momentum_table({"X": df}, dma_period=90)
        expected = {
            "symbol", "return_30d_pct", "return_60d_pct", "return_90d_pct",
            "return_180d_pct", "return_12mo_abs", "return_12mo_pct",
            "sharpe_ratio", "hit_rate_pct",
            "current_price", "week_52_high", "dma_value", "price_above_dma",
            "volume_participation_pct", "annual_traded_turnover_cr", "sector", "days_listed", "listing_date",
            "sector_avg_return_12mo_pct", "relative_to_sector_return_12mo_pct",
        }
        assert expected.issubset(set(table.columns))

    def test_includes_relative_momentum_columns(self, make_ohlcv):
        # Two symbols, same sector (via monkeypatched lookup would be needed
        # for a real sector match; here both get sector=None from
        # nse_master_data since these are fake symbols, so this just checks
        # the columns exist and don't raise, not the cross-sector math —
        # that's covered by TestAddRelativeMomentum above).
        df1 = make_ohlcv(n_days=280, daily_drift_pct=0.2, seed=19)
        df2 = make_ohlcv(n_days=280, daily_drift_pct=0.1, seed=20)
        table = me.build_momentum_table({"FAKE1": df1, "FAKE2": df2}, dma_period=90)
        assert "sector_avg_return_12mo_pct" in table.columns
        assert "relative_to_sector_return_12mo_pct" in table.columns
