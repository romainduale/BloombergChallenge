import pandas as pd

from src.compare_backtest_horizons import compare_horizons


def _periods(horizon: int, dates: list[str], returns: list[float]) -> pd.DataFrame:
    start = pd.to_datetime(dates)
    return pd.DataFrame(
        {
            "offset": 0,
            "date": start,
            "end_date": start + pd.to_timedelta(7 * horizon, unit="D"),
            f"net_return_{horizon}w": returns,
            f"benchmark_return_{horizon}w": [0.0] * len(start),
            f"net_excess_{horizon}w": returns,
            "one_way_turnover": [0.5] * len(start),
            "total_cost_return": [0.001] * len(start),
        }
    )


def test_comparison_uses_common_window_and_normalizes_turnover():
    weekly = _periods(
        1,
        ["2026-01-02", "2026-01-09", "2026-01-16", "2026-01-23", "2026-01-30"],
        [0.01] * 5,
    )
    five_week = _periods(5, ["2026-01-02"], [0.05])

    summary, by_path = compare_horizons(weekly, five_week)

    assert len(summary) == 2
    assert len(by_path) == 2
    annualized_turnover = summary.set_index("horizon_weeks")["annualized_one_way_turnover"]
    assert annualized_turnover.loc[1] == 26.0
    assert annualized_turnover.loc[5] == 5.2
