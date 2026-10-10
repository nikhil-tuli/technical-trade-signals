import datetime as dt

import numpy as np
import pandas as pd
import pytest

import algo_scanner as A

AFTER_CLOSE = dt.datetime(2026, 10, 10, 18, 0, tzinfo=A.IST)


def build(n=40, spike_at=None, pullback=True, spike_vol=500, flat=100.0):
    """Flat series (O=99.5,C=100,H=101,L=99,V=100) ending Fri 2026-10-09,
    with a bullish breakout candle at index spike_at, a higher high after
    it and (optionally) a drift back to the midpoint on the final candle."""
    idx = pd.bdate_range(end="2026-10-09", periods=n)
    o = np.full(n, flat - 0.5); h = np.full(n, flat + 1); l = np.full(n, flat - 1)
    c = np.full(n, flat); v = np.full(n, 100.0)
    if spike_at is not None:
        b = spike_at
        o[b], c[b], h[b], l[b], v[b] = 100, 108, 110, 99, spike_vol  # mid = 104.5
        if b + 1 < n:
            h[b + 1] = 115; c[b + 1] = 112; l[b + 1] = 108; o[b + 1] = 109
            for j in range(b + 2, n):
                o[j] = c[j] = 112; h[j] = 113; l[j] = 111
        if pullback and b + 1 < n:
            o[-1], c[-1], h[-1], l[-1] = 106, 104.8, 106, 104
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": v}, index=idx)


def test_detects_retest():
    r = A.scan_symbol("X", build(spike_at=30), now=AFTER_CLOSE)
    assert r and r["midpoint"] == 104.5 and r["days_since"] == 9
    assert r["vol_multiple"] == pytest.approx(5.0)
    assert r["distance_from_midpoint"] == pytest.approx((104.8 - 104.5) / 104.5 * 100)
    assert r["max_price_after"] == 115
    assert r["return_from_close_to_sub_high"] == pytest.approx((115 - 108) / 108 * 100)
    assert r["breakout_date"] == build(spike_at=30).index[30].date().isoformat()


def test_no_retest_when_price_far_from_midpoint():
    assert A.scan_symbol("X", build(spike_at=30, pullback=False), now=AFTER_CLOSE) is None


def test_age_boundary_inclusive_20_expires_21():
    n = 45
    assert A.scan_symbol("X", build(n=n, spike_at=n - 1 - 20), now=AFTER_CLOSE)["days_since"] == 20
    assert A.scan_symbol("X", build(n=n, spike_at=n - 1 - 21), now=AFTER_CLOSE) is None


def test_requires_higher_high_after_breakout():
    df = build(spike_at=30)
    df.loc[df.index[31:], "High"] = 109  # never exceeds breakout high 110
    assert A.scan_symbol("X", df, now=AFTER_CLOSE) is None


def test_low_volume_is_not_breakout():
    assert A.scan_symbol("X", build(spike_at=30, spike_vol=250), now=AFTER_CLOSE) is None


def test_bearish_candle_rejected():
    df = build(spike_at=30)
    df.loc[df.index[30], "Open"] = 109  # close 108 < open
    assert A.scan_symbol("X", df, now=AFTER_CLOSE) is None


def test_too_few_candles():
    assert A.scan_symbol("X", build(n=24), now=AFTER_CLOSE) is None


def test_newest_breakout_only_no_fallback_to_older():
    df = build(spike_at=25)
    # newer breakout at 35 that never retests (price stays at 112 > mid+1%)
    b = 35
    df.iloc[b] = [100, 130, 99, 120, 2000]
    df.iloc[b + 1:] = [125, 135, 124, 130, 100]
    # older candle 25 would have retested, but newest candle (35) fails -> reject
    df.iloc[-1] = [106, 106, 104, 104.8, 100]
    assert A.scan_symbol("X", df, now=AFTER_CLOSE) is None


def test_incomplete_candle_dropped_before_cutoff():
    df = build(spike_at=30)
    today = pd.DataFrame([df.iloc[-1].values], columns=df.columns,
                         index=[pd.Timestamp("2026-10-12")])
    df2 = pd.concat([df, today])
    midday = dt.datetime(2026, 10, 12, 11, 0, tzinfo=A.IST)
    r = A.scan_symbol("X", df2, now=midday)
    assert r and r["days_since"] == 9  # same as without the partial candle
    after = dt.datetime(2026, 10, 12, 17, 0, tzinfo=A.IST)
    assert A.scan_symbol("X", df2, now=after)["days_since"] == 10


def test_tz_aware_index_and_nan_rows():
    df = build(spike_at=30)
    df.index = df.index.tz_localize("Asia/Kolkata")
    df.iloc[3] = np.nan
    assert A.scan_symbol("X", df, now=AFTER_CLOSE) is not None


def test_zero_volume_baseline_skipped():
    df = build(spike_at=30)
    df.loc[df.index[10:30], "Volume"] = 0
    assert A.scan_symbol("X", df, now=AFTER_CLOSE) is None


def test_scan_universe_sort_and_progress():
    a = build(spike_at=30); b = build(spike_at=33); bad = build(n=10)
    calls = []
    res, total = A.scan_universe({"A": a, "B": b, "C": bad},
                                 progress_callback=lambda *x: calls.append(x), now=AFTER_CLOSE)
    assert total == 3 and [r["symbol"] for r in res] == ["B", "A"]
    assert calls[-1] == (3, 3, 2)
    t = A.results_to_table(res)
    assert list(t["Rank"]) == [1, 2] and t.columns[0] == "Rank"


def test_data_session_key():
    sat = dt.datetime(2026, 10, 10, 12, 0, tzinfo=A.IST)
    assert A.data_session_key(sat) == dt.date(2026, 10, 9)
    mon_morning = dt.datetime(2026, 10, 12, 10, 0, tzinfo=A.IST)
    assert A.data_session_key(mon_morning) == dt.date(2026, 10, 9)
    mon_eve = dt.datetime(2026, 10, 12, 17, 0, tzinfo=A.IST)
    assert A.data_session_key(mon_eve) == dt.date(2026, 10, 12)
