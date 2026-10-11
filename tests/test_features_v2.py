import numpy as np
import pandas as pd
import pytest

from src.features_v2 import (
    compute_eps_revision,
    compute_residual_features,
    compute_sortino,
)


def test_sortino_penalizes_downside_risk():
    index = pd.date_range("2025-01-03", periods=6, freq="W-FRI")
    returns = pd.DataFrame(
        {
            "stable": [0.01, 0.01, -0.01, 0.01, 0.01, -0.01],
            "volatile": [0.03, -0.08, 0.03, 0.03, -0.08, 0.03],
        },
        index=index,
    )
    result = compute_sortino(returns, window=6, min_periods=6)
    assert result.loc[index[-1], "stable"] > result.loc[index[-1], "volatile"]


def test_residual_features_remove_benchmark_component():
    index = pd.date_range("2024-01-05", periods=12, freq="W-FRI")
    benchmark = pd.Series(np.linspace(-0.02, 0.03, 12), index=index)
    stock = pd.DataFrame(
        {
            "market_like": 2.0 * benchmark,
            "independent": np.sin(np.arange(12)) * 0.01,
        },
        index=index,
    )
    momentum, ivol = compute_residual_features(
        stock,
        benchmark,
        regression_window=6,
        signal_window=4,
        min_regression_periods=4,
        min_signal_periods=3,
    )
    assert abs(ivol["market_like"].dropna().iloc[-1]) < 1e-10
    assert np.isfinite(momentum["independent"].dropna().iloc[-1])


def test_eps_revision_is_lagged_before_weekly_use(tmp_path):
    path = tmp_path / "eps.csv"
    pd.DataFrame(
        {
            "month": ["2025-01", "2025-02", "2025-03", "2025-04"],
            "A": [1.0, 1.0, 1.0, 2.0],
        }
    ).to_csv(path, index=False)
    weekly = pd.DatetimeIndex(["2025-04-25", "2025-05-30", "2025-06-06"])
    result = compute_eps_revision(
        weekly,
        pd.Index(["A"]),
        path=path,
        revision_months=3,
        availability_lag_months=1,
    )
    assert np.isnan(result.loc[pd.Timestamp("2025-04-25"), "A"])
    assert np.isnan(result.loc[pd.Timestamp("2025-05-30"), "A"])
    assert result.loc[pd.Timestamp("2025-06-06"), "A"] == pytest.approx(1.0)
