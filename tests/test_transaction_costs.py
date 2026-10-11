import pandas as pd
import pytest

from src.trading_config import ExecutionConfig
from src.transaction_costs import calculate_turnover, drift_weights


def test_initial_investment_has_100_percent_turnover_and_costs():
    config = ExecutionConfig(commission_bps=10, slippage_bps=5)
    result = calculate_turnover(
        {},
        {"A": 0.6, "B": 0.4},
        config,
        previous_cash_weight=1.0,
        target_cash_weight=0.0,
    )
    assert result.one_way_turnover == pytest.approx(1.0)
    assert result.traded_notional == pytest.approx(1.0)
    assert result.transaction_cost_return == pytest.approx(0.0015)


def test_rebalance_turnover_uses_union_of_assets():
    config = ExecutionConfig(commission_bps=10, slippage_bps=0)
    result = calculate_turnover(
        {"A": 0.6, "B": 0.4},
        {"A": 0.5, "C": 0.5},
        config,
        previous_cash_weight=0.0,
        target_cash_weight=0.0,
    )
    assert result.traded_notional == pytest.approx(1.0)
    assert result.one_way_turnover == pytest.approx(0.5)
    assert result.transaction_cost_return == pytest.approx(0.001)


def test_drift_weights_after_returns():
    weights, cash = drift_weights(
        pd.Series({"A": 0.5, "B": 0.5}),
        pd.Series({"A": 0.10, "B": 0.0}),
    )
    assert weights["A"] == pytest.approx(0.55 / 1.05)
    assert weights["B"] == pytest.approx(0.50 / 1.05)
    assert cash == 0.0


def test_weight_cap_above_twenty_percent_is_rejected():
    with pytest.raises(ValueError, match="20 %"):
        ExecutionConfig(max_position_weight=0.21)
