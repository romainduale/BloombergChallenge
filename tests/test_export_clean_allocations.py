import pandas as pd
import pytest

from src.export_clean_allocations import build_clean_allocation_exports


def test_clean_exports_split_sleeves_and_recalculate_readable_values():
    allocation = pd.DataFrame(
        {
            "id": ["CORE FP Equity", "OPP UW Equity", "ZERO UN Equity"],
            "sleeve": ["core_5w", "opportunistic", "core_5w"],
            "weight": [0.80, 0.20, 1e-18],
            "combined_score": [0.95, 0.90, 0.80],
            "opportunity_score": [pd.NA, 75.0, pd.NA],
            "predicted_excess_return": [0.03, 0.04, 0.01],
            "currency": ["EUR", "USD", "USD"],
        }
    )
    orders = pd.DataFrame(
        {
            "id": ["CORE FP Equity", "OPP UW Equity", "ZERO UN Equity"],
            "last_price": [50.0, 100.0, 10.0],
            "price_to_usd_rate": [1.10, 1.0, 1.0],
        }
    )

    core, opportunistic = build_clean_allocation_exports(
        allocation,
        orders,
        capital=1_000_000,
    )

    assert core["id"].tolist() == ["CORE FP Equity"]
    assert core.loc[0, "allocation_pct"] == pytest.approx(80.0)
    assert core.loc[0, "allocation_usd"] == pytest.approx(800_000.0)
    assert core.loc[0, "last_price_usd"] == pytest.approx(55.0)
    assert core.loc[0, "score"] == pytest.approx(95.0)
    assert core.loc[0, "estimated_excess_profit_5w_usd"] == pytest.approx(24_000.0)

    assert opportunistic["id"].tolist() == ["OPP UW Equity"]
    assert opportunistic.loc[0, "allocation_pct"] == pytest.approx(20.0)
    assert opportunistic.loc[0, "score"] == pytest.approx(75.0)
    assert opportunistic.loc[0, "estimated_excess_profit_5w_usd"] == pytest.approx(8_000.0)
