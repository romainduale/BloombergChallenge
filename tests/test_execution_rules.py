import numpy as np
import pandas as pd
import pytest

from src.build_execution_plan import load_price_to_usd_rates
from src.execution_rules import (
    build_execution_orders,
    simulate_limit_buy,
    simulate_stop_loss,
    stop_distance,
)
from src.trading_config import ExecutionConfig


def test_fixed_stop_executes_on_next_available_close():
    dates = pd.bdate_range("2026-01-01", periods=30)
    prices = pd.Series(np.full(30, 100.0), index=dates)
    prices.iloc[21] = 89.0
    prices.iloc[22] = 88.0
    config = ExecutionConfig(
        stop_loss_mode="fixed",
        fixed_stop_loss_pct=0.10,
        stop_execution_delay_days=1,
    )

    result = simulate_stop_loss(prices, dates[20], dates[-1], config)
    assert result.stopped
    assert result.trigger_date == dates[21]
    assert result.exit_date == dates[22]
    assert result.realised_return == pytest.approx(-0.12)


def test_volatility_stop_is_clipped_to_configured_band():
    config = ExecutionConfig(
        stop_loss_mode="volatility",
        volatility_multiplier=2.0,
        minimum_stop_pct=0.05,
        maximum_stop_pct=0.15,
    )
    assert stop_distance(config, daily_volatility=0.001) == pytest.approx(0.05)
    assert stop_distance(config, daily_volatility=0.20) == pytest.approx(0.15)


def test_limit_buy_uses_discount_and_validity_window():
    dates = pd.bdate_range("2026-01-01", periods=8)
    prices = pd.Series([100, 100, 99.7, 99.4, 99.0, 98.0, 101, 102], index=dates)
    config = ExecutionConfig(limit_discount_pct=0.005, limit_valid_days=3)
    result = simulate_limit_buy(prices, dates[1], config)
    assert result.limit_price == pytest.approx(99.5)
    assert result.filled
    assert result.fill_date == dates[3]


def test_orders_cover_buy_hold_reduce_and_sell():
    config = ExecutionConfig(
        minimum_trade_weight=0.01,
        stop_loss_mode="fixed",
        fixed_stop_loss_pct=0.10,
    )
    orders = build_execution_orders(
        pd.Series({"BUY": 0.10, "HOLD": 0.10, "REDUCE": 0.05, "SELL": 0.0}),
        pd.Series({"BUY": 0.0, "HOLD": 0.105, "REDUCE": 0.10, "SELL": 0.10}),
        pd.Series({"BUY": 100.0, "HOLD": 100.0, "REDUCE": 100.0, "SELL": 100.0}),
        config,
        as_of=pd.Timestamp("2026-10-09"),
    ).set_index("id")

    assert orders.loc["BUY", "action"] == "BUY"
    assert orders.loc["HOLD", "action"] == "HOLD"
    assert orders.loc["REDUCE", "action"] == "REDUCE"
    assert orders.loc["SELL", "action"] == "SELL"
    assert orders.loc["BUY", "share_estimate_status"] == "FX_REQUIRED"


def test_share_estimate_requires_an_explicit_fx_conversion():
    config = ExecutionConfig(stop_loss_mode="none")
    orders = build_execution_orders(
        pd.Series({"JPY_ASSET": 0.10}),
        pd.Series(dtype=float),
        pd.Series({"JPY_ASSET": 20_000.0}),
        config,
        as_of=pd.Timestamp("2026-10-09"),
        capital=1_000_000,
        price_to_usd_rates=pd.Series({"JPY_ASSET": 0.0067}),
    ).set_index("id")

    assert orders.loc["JPY_ASSET", "estimated_shares"] == 746
    assert orders.loc["JPY_ASSET", "share_estimate_status"] == "READY"


def test_existing_position_below_protective_stop_becomes_stop_sale():
    config = ExecutionConfig(
        minimum_trade_weight=0.01,
        stop_loss_mode="fixed",
        fixed_stop_loss_pct=0.10,
    )
    orders = build_execution_orders(
        pd.Series({"A": 0.10}),
        pd.Series({"A": 0.10}),
        pd.Series({"A": 89.0}),
        config,
        as_of=pd.Timestamp("2026-10-09"),
        entry_prices=pd.Series({"A": 100.0}),
    ).set_index("id")

    assert orders.loc["A", "action"] == "SELL_STOP"
    assert orders.loc["A", "order_type"] == "MARKET_SELL"
    assert orders.loc["A", "trade_weight"] == pytest.approx(-0.10)


def test_execution_plan_maps_latest_fx_rate_by_asset(tmp_path):
    static_path = tmp_path / "static.csv"
    fx_path = tmp_path / "fx.csv"
    pd.DataFrame({"id": ["USD_ASSET", "JPY_ASSET"], "currency": ["USD", "JPY"]}).to_csv(
        static_path, index=False
    )
    pd.DataFrame(
        {
            "date": ["2026-10-09", "2026-10-12"],
            "currency": ["JPY", "JPY"],
            "usd_rate": [0.0066, 0.0067],
        }
    ).to_csv(fx_path, index=False)

    rates = load_price_to_usd_rates(
        pd.Index(["USD_ASSET", "JPY_ASSET"]),
        pd.Timestamp("2026-10-12"),
        static_path=static_path,
        fx_path=fx_path,
    )

    assert rates["USD_ASSET"] == pytest.approx(1.0)
    assert rates["JPY_ASSET"] == pytest.approx(0.0067)


def test_execution_plan_infers_missing_currency_from_bloomberg_exchange(tmp_path):
    static_path = tmp_path / "static.csv"
    fx_path = tmp_path / "fx.csv"
    pd.DataFrame(
        {
            "id": ["AAPL UW Equity", "6981 JT Equity"],
            "currency": [pd.NA, pd.NA],
        }
    ).to_csv(static_path, index=False)
    pd.DataFrame(
        {
            "date": ["2026-10-14", "2026-10-14"],
            "currency": ["USD", "JPY"],
            "usd_rate": [1.0, 0.0063],
        }
    ).to_csv(fx_path, index=False)

    rates = load_price_to_usd_rates(
        pd.Index(["AAPL UW Equity", "6981 JT Equity"]),
        pd.Timestamp("2026-10-14"),
        static_path=static_path,
        fx_path=fx_path,
    )

    assert rates["AAPL UW Equity"] == pytest.approx(1.0)
    assert rates["6981 JT Equity"] == pytest.approx(0.0063)
