from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.elastic_net_transversal import FEATURES, ElasticNetConfig
from src.opportunistic_model import OpportunisticConfig
from src.strategies.final_four_week.compare_profiles import ranking_for_profile
from src.strategies.final_four_week.config import load_strategy_profiles
from src.strategies.final_four_week.constants import FEATURE_LABELS, TARGET_4W
from src.strategies.final_four_week.export import build_final_explained_export
from src.strategies.final_four_week.features import build_panel_4w
from src.strategies.final_four_week.models import fit_latest_four_week_models
from src.strategies.final_four_week.pipeline import combine_80_20


def test_four_week_target_ends_exactly_four_fridays_later():
    dates = pd.bdate_range("2026-09-01", "2026-11-13")
    prices = pd.DataFrame(
        {
            "A": np.linspace(100.0, 130.0, len(dates)),
            "B": np.linspace(100.0, 115.0, len(dates)),
        },
        index=dates,
    )
    volumes = pd.DataFrame(1_000.0, index=dates, columns=prices.columns)
    benchmark = pd.Series(np.linspace(100.0, 110.0, len(dates)), index=dates)

    panel = build_panel_4w(prices, volumes, benchmark)
    signal = panel[panel["date"].eq(pd.Timestamp("2026-10-16"))].set_index("id")
    weekly_prices = prices.resample("W-FRI").last()
    weekly_benchmark = benchmark.resample("W-FRI").last()
    expected = (
        weekly_prices.loc["2026-11-13", "A"] / weekly_prices.loc["2026-10-16", "A"]
        - 1.0
        - (weekly_benchmark.loc["2026-11-13"] / weekly_benchmark.loc["2026-10-16"] - 1.0)
    )
    assert signal.loc["A", TARGET_4W] == pytest.approx(expected)


def test_strategy_profiles_span_prudent_to_aggressive_and_change_ranking():
    profiles = load_strategy_profiles()
    assert set(profiles) == {"prudent", "intermediaire", "agressif"}
    assert profiles["prudent"].kappa > profiles["intermediaire"].kappa
    assert profiles["intermediaire"].kappa > profiles["agressif"].kappa
    assert profiles["prudent"].max_position_weight < profiles["agressif"].max_position_weight
    assert profiles["prudent"].tail_weight < profiles["agressif"].tail_weight

    opposing_signals = pd.DataFrame(
        {
            "id": ["TAIL", "ELASTIC"],
            "tail_rank": [1.0, 0.0],
            "elastic_net_rank": [0.0, 1.0],
        }
    )
    prudent = ranking_for_profile(opposing_signals, profiles["prudent"])
    aggressive = ranking_for_profile(opposing_signals, profiles["agressif"])
    assert prudent.loc[prudent["id"].eq("TAIL"), "combined_score"].iloc[0] == pytest.approx(0.50)
    assert aggressive.iloc[0]["id"] == "TAIL"


def test_latest_models_export_scores_betas_and_contributions():
    dates = pd.date_range("2022-01-07", periods=210, freq="W-FRI")
    ids = [f"ASSET_{index}" for index in range(12)]
    rows = []
    for date_index, date in enumerate(dates):
        for asset_index, asset in enumerate(ids):
            values = {
                feature: ((asset_index + feature_index + date_index % 7) % 12) / 11.0
                for feature_index, feature in enumerate(FEATURES)
            }
            target = 0.02 * values[FEATURES[0]] - 0.01 * values[FEATURES[3]]
            rows.append({"date": date, "id": asset, TARGET_4W: target, **values})
    panel = pd.DataFrame(rows)
    panel.loc[panel["date"].isin(dates[-4:]), TARGET_4W] = np.nan
    config = ElasticNetConfig(
        train_years=3,
        purge_weeks=4,
        test_every_n_weeks=4,
        min_train_rows=100,
        min_test_rows=5,
    )

    result = fit_latest_four_week_models(panel, config)

    assert {"elastic_net_score", "tail_score", "combined_score"}.issubset(result.ranking)
    assert set(result.coefficients["model"]) == {"elastic_net", "tail"}
    assert len(result.coefficients) == 2 * len(FEATURES)
    for label in FEATURE_LABELS.values():
        assert f"elastic_beta_{label}" in result.ranking
        assert f"tail_beta_{label}" in result.ranking
        assert f"elastic_contribution_{label}" in result.ranking
        assert f"tail_contribution_{label}" in result.ranking


def test_final_export_contains_model_explanations_for_both_sleeves():
    labels = list(FEATURE_LABELS.values())
    assets = [
        "CORE1 UN Equity",
        "CORE2 UN Equity",
        "CORE3 UN Equity",
        "CORE4 UN Equity",
        "OPP UW Equity",
    ]
    diagnostics = {
        f"{prefix}_{kind}_{label}": [0.1, 0.1, 0.1, 0.1, 0.2]
        for label in labels
        for prefix, kind in (
            ("elastic", "beta"),
            ("elastic", "contribution"),
            ("tail", "beta"),
            ("tail", "contribution"),
        )
    }
    diagnostics.update({f"feature_{label}": [0.4, 0.4, 0.4, 0.4, 0.6] for label in labels})
    signal = pd.DataFrame(
        {
            "id": assets,
            "date": ["2026-10-16"] * len(assets),
            "elastic_net_score": [0.03, 0.029, 0.028, 0.027, 0.02],
            "elastic_net_rank": [0.99, 0.98, 0.97, 0.96, 0.90],
            "tail_score": [0.74, 0.73, 0.72, 0.71, 0.65],
            "tail_rank": [0.99, 0.98, 0.97, 0.96, 0.89],
            "combined_score": [0.99, 0.98, 0.97, 0.96, 0.8925],
            "combined_rank": [1.0, 0.98, 0.96, 0.94, 0.9],
            "selection_explanation": ["Elastic et Tail"] * len(assets),
            **diagnostics,
        }
    )
    core = pd.DataFrame({"id": assets[:4], "weight": [0.25] * 4})
    opportunity = pd.DataFrame(
        {
            "id": ["OPP UW Equity"],
            "weight": [0.20],
            "currency": ["USD"],
            "opportunity_score": [75.0],
            "reason": ["Momentum positif"],
            # Ces colonnes existent dans la vraie sortie opportuniste. L'export doit
            # utiliser les valeurs du plan d'ordres sans créer de suffixes _x/_y.
            "last_price": [49.0],
            "price_to_usd_rate": [0.99],
        }
    )
    config = OpportunisticConfig(
        opportunistic_positions=1,
        max_opportunistic_position_weight=0.20,
    )
    allocation = combine_80_20(core, opportunity, config)
    orders = pd.DataFrame(
        {
            "id": assets,
            "last_price": [100.0, 100.0, 100.0, 100.0, 50.0],
            "price_to_usd_rate": [1.0] * len(assets),
            "action": ["BUY"] * len(assets),
            "quantity": [2000, 2000, 2000, 2000, 4000],
        }
    )

    final = build_final_explained_export(
        allocation,
        orders,
        signal,
        capital=1_000_000.0,
    )

    assert final["allocation_pct"].sum() == pytest.approx(100.0)
    assert final["planned_exit_date"].eq(pd.Timestamp("2026-11-13")).all()
    assert final["challenge_aligned"].all()
    assert {"elastic_net_score", "tail_score"}.issubset(final)
    assert "elastic_beta_momentum_1m" in final
    assert "tail_contribution_distance_52w_high" in final
    assert final["data_quality"].eq("OK").all()
    assert final.loc[final["id"].eq("OPP UW Equity"), "last_price_local"].iloc[0] == 50.0
    assert (
        "Opportuniste: Momentum positif"
        in final.loc[final["sleeve"].eq("opportunistic"), "selection_explanation"].iloc[0]
    )
