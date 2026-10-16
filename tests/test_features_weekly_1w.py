import pandas as pd
import pytest

from src.features import compute_target


def test_one_week_target_uses_next_week_relative_return():
    dates = pd.date_range("2026-01-02", periods=3, freq="W-FRI")
    prices = pd.DataFrame({"A": [100.0, 110.0, 121.0]}, index=dates)
    benchmark = pd.Series([100.0, 105.0, 110.25], index=dates)

    target = compute_target(prices, benchmark, horizon_weeks=1)

    assert target.loc[dates[0], "A"] == pytest.approx(0.05)
    assert target.loc[dates[1], "A"] == pytest.approx(0.05)
    assert pd.isna(target.loc[dates[2], "A"])
