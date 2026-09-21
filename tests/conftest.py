"""
Shared fixtures. synthetic_ohlcv() is deterministic (seeded) so every
test using it gets the exact same numbers run to run — no flaky tests
from random data.
"""
import numpy as np
import pandas as pd
import pytest


def _make_ohlcv(n_days: int, daily_drift_pct: float = 0.0, start_price: float = 100.0,
                 volume: int = 1_000_000, seed: int = 42, volume_spike_last_n: int | None = None) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n_days)
    # Some pandas versions have shown off-by-one edge cases in bdate_range's
    # `periods` count depending on what "today" falls on (observed: pandas
    # 3.0.2 returning n_days-1 rows for certain dates). Rather than trust
    # `periods` blindly, size every array off the INDEX'S ACTUAL length —
    # this makes the fixture correct regardless of pandas version or which
    # day it happens to run on.
    actual_n = len(dates)

    daily_returns = rng.normal(loc=daily_drift_pct / 100, scale=0.005, size=actual_n)
    close = start_price * np.cumprod(1 + daily_returns)
    open_ = np.concatenate([[start_price], close[:-1]])
    high = np.maximum(open_, close) * 1.002
    low = np.minimum(open_, close) * 0.998
    vol = np.full(actual_n, volume, dtype=float)
    if volume_spike_last_n:
        vol[-volume_spike_last_n:] *= 2.5

    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol},
        index=dates,
    )


@pytest.fixture
def make_ohlcv():
    """Factory fixture — call make_ohlcv(n_days=300, daily_drift_pct=0.15) etc."""
    return _make_ohlcv
