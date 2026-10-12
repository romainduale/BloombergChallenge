import pandas as pd
import pytest

from src.audit_backtest import max_drawdown, summarize_group


def test_max_drawdown_uses_compounded_wealth():
    drawdown = max_drawdown(pd.Series([0.10, -0.20, 0.05]))
    assert drawdown == pytest.approx(-0.20)


def test_summary_reports_costs_turnover_and_relative_return():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-03", "2025-02-07"]),
            "end_date": pd.to_datetime(["2025-02-07", "2025-03-14"]),
            "gross_return_5w": [0.05, 0.02],
            "net_return_5w": [0.049, 0.019],
            "benchmark_return_5w": [0.02, 0.01],
            "net_excess_5w": [0.029, 0.009],
            "one_way_turnover": [1.0, 0.2],
            "total_cost_return": [0.001, 0.001],
            "n_stops": [0, 1],
            "limit_fills": [2, 1],
            "limit_candidates": [2, 2],
            "max_weight": [0.20, 0.20],
        }
    )
    summary = summarize_group(frame)
    assert summary["win_rate"] == 1.0
    assert summary["average_one_way_turnover"] == pytest.approx(0.6)
    assert summary["total_cost_return"] == pytest.approx(0.002)
    assert summary["limit_fill_rate"] == pytest.approx(0.75)
