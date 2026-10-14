import numpy as np
import pandas as pd
import pytest

from src.market_metadata import infer_currency
from src.opportunistic_model import (
    OpportunisticConfig,
    bloomberg_to_yahoo,
    build_opportunistic_portfolio,
    combine_allocations,
    compute_opportunity_scores,
)


def test_bloomberg_to_yahoo_maps_common_exchanges():
    assert bloomberg_to_yahoo("IONQ UN") == "IONQ"
    assert bloomberg_to_yahoo("6981 JT") == "6981.T"
    assert bloomberg_to_yahoo("700 HK") == "0700.HK"
    assert bloomberg_to_yahoo("005930 KP") == "005930.KS"
    assert bloomberg_to_yahoo("AAPL UW Equity") == "AAPL"
    assert bloomberg_to_yahoo("NESN SE") == "NESN.SW"
    assert bloomberg_to_yahoo("CABK SQ") == "CABK.MC"
    assert bloomberg_to_yahoo("BP/ LN") == "BP.L"
    assert bloomberg_to_yahoo("WALMEX* MF") == "WALMEX.MX"
    assert bloomberg_to_yahoo("UNKNOWN XX") is None


def test_currency_is_inferred_from_bloomberg_exchange():
    assert infer_currency("AAPL UW Equity") == "USD"
    assert infer_currency("6981 JT Equity") == "JPY"
    assert infer_currency("005930 KP Equity") == "KRW"
    assert infer_currency("STMPA FP Equity") == "EUR"
    assert infer_currency("700 HK Equity") == "HKD"
    assert infer_currency("CSL AT Equity") == "AUD"
    assert infer_currency("UNKNOWN XX Equity") is None


def test_opportunity_scores_and_combined_allocation_are_bounded():
    dates = pd.bdate_range("2025-01-01", periods=180)
    ids = ["A", "B", "C", "D", "E", "F"]
    prices = pd.DataFrame(index=dates)
    volumes = pd.DataFrame(index=dates)
    for index, asset in enumerate(ids):
        prices[asset] = 100.0 * np.cumprod(np.repeat(1.0003 + 0.0001 * index, len(dates)))
        volumes[asset] = 1_000_000 + 100_000 * index

    candidates = pd.DataFrame(
        {
            "id": ids,
            "yahoo_ticker": ids,
            "name": ids,
            "currency": "USD",
            "combined_score": np.linspace(0.8, 1.0, len(ids)),
            "predicted_excess_return": np.linspace(0.01, 0.04, len(ids)),
        }
    )
    config = OpportunisticConfig(minimum_average_dollar_volume_usd=1_000_000)
    scores = compute_opportunity_scores(
        prices,
        volumes,
        candidates,
        pd.Series({"USD": 1.0}),
        config,
        today=dates[-1],
    )

    assert scores["eligible"].all()
    assert scores["opportunity_score"].between(0, 100).all()
    sleeve = build_opportunistic_portfolio(scores, {"A"}, config)
    assert len(sleeve) == 4
    assert sleeve["weight"].max() == pytest.approx(0.05)
    assert sleeve["weight"].sum() == pytest.approx(0.20)

    core = pd.DataFrame(
        {
            "id": ["CORE1", "CORE2", "CORE3", "CORE4", "CORE5"],
            "weight": [0.2, 0.2, 0.2, 0.2, 0.2],
        }
    )
    combined = combine_allocations(core, sleeve, config)
    assert combined["weight"].sum() == pytest.approx(1.0)
    assert combined.loc[combined["sleeve"].eq("core_5w"), "weight"].sum() == pytest.approx(
        0.80
    )
    assert combined.loc[
        combined["sleeve"].eq("opportunistic"), "weight"
    ].sum() == pytest.approx(0.20)
