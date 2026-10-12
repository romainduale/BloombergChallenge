import pandas as pd

from src.compare_execution_profiles import compare_profiles


def _periods(net_returns: list[float], stops: list[int]) -> pd.DataFrame:
    dates = pd.date_range("2025-01-03", periods=len(net_returns), freq="5W-FRI")
    return pd.DataFrame(
        {
            "offset": [0] * len(net_returns),
            "date": dates,
            "end_date": dates + pd.Timedelta(weeks=5),
            "gross_return_5w": net_returns,
            "net_return_5w": net_returns,
            "benchmark_return_5w": [0.0] * len(net_returns),
            "gross_excess_5w": net_returns,
            "net_excess_5w": net_returns,
            "one_way_turnover": [0.5] * len(net_returns),
            "total_cost_return": [0.001] * len(net_returns),
            "n_stops": stops,
            "limit_candidates": [2] * len(net_returns),
            "limit_fills": [1] * len(net_returns),
            "limit_fill_rate": [0.5] * len(net_returns),
            "max_weight": [0.20] * len(net_returns),
        }
    )


def test_compare_profiles_matches_periods_against_baseline() -> None:
    result = compare_profiles(
        {
            "sans_stop": _periods([0.01, -0.02], [0, 0]),
            "stop_fixe": _periods([0.02, -0.01], [1, 1]),
        }
    ).set_index("profile")

    assert result.loc["stop_fixe", "matched_periods_vs_baseline"] == 2
    assert result.loc["stop_fixe", "mean_net_return_delta_vs_baseline"] == 0.01
    assert result.loc["stop_fixe", "period_improvement_rate_vs_baseline"] == 1.0
