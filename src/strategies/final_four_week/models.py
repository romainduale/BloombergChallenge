from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

from src.backtest_portfolio_v1 import make_elastic_model, make_tail_model
from src.elastic_net_transversal import FEATURES, ElasticNetConfig
from src.strategies.final_four_week.config import (
    DEFAULT_STRATEGY_PROFILE,
    StrategyProfile,
    load_strategy_profile,
)
from src.strategies.final_four_week.constants import (
    COEFFICIENTS_PATH,
    FEATURE_LABELS,
    HORIZON_WEEKS,
    PANEL_PATH,
    SIGNAL_PATH,
    TARGET_4W,
)


@dataclass(frozen=True)
class LatestModelResult:
    ranking: pd.DataFrame
    coefficients: pd.DataFrame
    train_start: pd.Timestamp
    train_end: pd.Timestamp


def four_week_model_config() -> ElasticNetConfig:
    return ElasticNetConfig(
        purge_weeks=HORIZON_WEEKS,
        test_every_n_weeks=HORIZON_WEEKS,
    )


def prepare_four_week_training_data(panel: pd.DataFrame) -> pd.DataFrame:
    data = panel.dropna(subset=FEATURES + [TARGET_4W]).copy()
    threshold = data.groupby("date")[TARGET_4W].transform(lambda values: values.quantile(0.90))
    data["tail_target"] = data[TARGET_4W].ge(threshold).astype(int)
    return data.sort_values(["date", "id"]).reset_index(drop=True)


def _coefficient_table(model: Pipeline, model_name: str) -> pd.DataFrame:
    scaler = model.named_steps["scaler"]
    estimator = model.named_steps["model"]
    beta_standardized = np.asarray(estimator.coef_, dtype=float).reshape(-1)
    scale = np.asarray(scaler.scale_, dtype=float)
    mean = np.asarray(scaler.mean_, dtype=float)
    beta_raw = np.divide(
        beta_standardized,
        scale,
        out=np.zeros_like(beta_standardized),
        where=scale != 0,
    )
    intercept_standardized = float(np.asarray(estimator.intercept_).reshape(-1)[0])
    intercept_raw = intercept_standardized - float(beta_raw @ mean)
    return pd.DataFrame(
        {
            "model": model_name,
            "feature": FEATURES,
            "feature_label": [FEATURE_LABELS[feature] for feature in FEATURES],
            "beta_standardized": beta_standardized,
            "beta_original_scale": beta_raw,
            "scaler_mean": mean,
            "scaler_scale": scale,
            "intercept_standardized": intercept_standardized,
            "intercept_original_scale": intercept_raw,
        }
    )


def _add_model_diagnostics(
    latest: pd.DataFrame,
    model: Pipeline,
    *,
    prefix: str,
) -> None:
    scaler = model.named_steps["scaler"]
    estimator = model.named_steps["model"]
    standardized = scaler.transform(latest[FEATURES])
    coefficients = np.asarray(estimator.coef_, dtype=float).reshape(-1)
    contributions = standardized * coefficients

    for feature_index, feature in enumerate(FEATURES):
        label = FEATURE_LABELS[feature]
        latest[f"feature_{label}"] = latest[feature].astype(float)
        latest[f"{prefix}_beta_{label}"] = coefficients[feature_index]
        latest[f"{prefix}_contribution_{label}"] = contributions[:, feature_index]


def _explain_row(row: pd.Series) -> str:
    explanations = []
    for prefix, title in (("elastic", "Elastic"), ("tail", "Tail")):
        contribution_columns = {
            label: f"{prefix}_contribution_{label}" for label in FEATURE_LABELS.values()
        }
        ordered = sorted(
            contribution_columns,
            key=lambda label: abs(float(row[contribution_columns[label]])),
            reverse=True,
        )[:2]
        details = ", ".join(
            f"{label}={float(row[contribution_columns[label]]):+.4f}" for label in ordered
        )
        explanations.append(f"{title}: {details}")
    return " | ".join(explanations)


def fit_latest_four_week_models(
    panel: pd.DataFrame,
    config: ElasticNetConfig | None = None,
    *,
    strategy_profile: StrategyProfile | None = None,
) -> LatestModelResult:
    cfg = config or four_week_model_config()
    profile = strategy_profile or load_strategy_profile(DEFAULT_STRATEGY_PROFILE)
    panel = panel.copy()
    panel["date"] = pd.to_datetime(panel["date"])
    feature_data = panel.dropna(subset=FEATURES)
    if feature_data.empty:
        raise ValueError("Aucune ligne ne contient toutes les features.")

    latest_date = pd.Timestamp(feature_data["date"].max())
    latest = feature_data[feature_data["date"].eq(latest_date)].copy()
    historical = prepare_four_week_training_data(panel)
    train_end = latest_date - pd.Timedelta(weeks=cfg.purge_weeks)
    train_start = train_end - pd.DateOffset(years=cfg.train_years)
    train = historical[historical["date"].ge(train_start) & historical["date"].lt(train_end)]
    if len(train) < cfg.min_train_rows:
        raise ValueError(
            f"Historique insuffisant : {len(train):,} lignes, minimum {cfg.min_train_rows:,}."
        )
    if train["tail_target"].nunique() < 2:
        raise ValueError("La cible Tail ne contient pas les deux classes dans l'apprentissage.")

    elastic = make_elastic_model(cfg)
    tail = make_tail_model()
    elastic.fit(train[FEATURES], train[TARGET_4W])
    tail.fit(train[FEATURES], train["tail_target"])

    latest["elastic_net_score"] = elastic.predict(latest[FEATURES])
    latest["tail_score"] = tail.predict_proba(latest[FEATURES])[:, 1]
    latest["elastic_net_rank"] = latest["elastic_net_score"].rank(pct=True, method="average")
    latest["tail_rank"] = latest["tail_score"].rank(pct=True, method="average")
    latest["combined_score"] = (
        profile.elastic_weight * latest["elastic_net_rank"]
        + profile.tail_weight * latest["tail_rank"]
    )
    latest["combined_rank"] = latest["combined_score"].rank(pct=True, method="average")

    _add_model_diagnostics(latest, elastic, prefix="elastic")
    _add_model_diagnostics(latest, tail, prefix="tail")
    latest["selection_explanation"] = latest.apply(_explain_row, axis=1)

    # Alias conservé pour les briques historiques de risque et de la poche 20 %.
    latest["predicted_excess_return"] = latest["elastic_net_score"]
    latest["predicted_rank"] = latest["elastic_net_rank"]
    latest["elastic_rank"] = latest["elastic_net_rank"]
    latest["tail_probability"] = latest["tail_score"]
    latest["horizon_weeks"] = HORIZON_WEEKS
    latest["strategy_profile"] = profile.name
    ranking = latest.sort_values("combined_score", ascending=False).reset_index(drop=True)

    coefficients = pd.concat(
        [
            _coefficient_table(elastic, "elastic_net"),
            _coefficient_table(tail, "tail"),
        ],
        ignore_index=True,
    )
    coefficients.insert(0, "signal_date", latest_date)
    coefficients.insert(1, "train_start", train_start)
    coefficients.insert(2, "train_end_exclusive", train_end)
    coefficients.insert(3, "horizon_weeks", HORIZON_WEEKS)
    return LatestModelResult(ranking, coefficients, train_start, train_end)


def create_latest_signal(
    panel_path: Path = PANEL_PATH,
    signal_path: Path = SIGNAL_PATH,
    coefficients_path: Path = COEFFICIENTS_PATH,
    *,
    strategy_profile: StrategyProfile | None = None,
) -> LatestModelResult:
    panel = pd.read_csv(panel_path, parse_dates=["date"])
    result = fit_latest_four_week_models(panel, strategy_profile=strategy_profile)
    signal_path.parent.mkdir(parents=True, exist_ok=True)
    result.ranking.to_csv(signal_path, index=False)
    result.coefficients.to_csv(coefficients_path, index=False)
    return result


def main() -> None:
    result = create_latest_signal()
    columns = [
        "date",
        "id",
        "elastic_net_score",
        "elastic_net_rank",
        "tail_score",
        "tail_rank",
        "combined_score",
    ]
    print(result.ranking[columns].head(30).to_string(index=False))
    print(f"\nSignal : {SIGNAL_PATH}")
    print(f"Bêta : {COEFFICIENTS_PATH}")


if __name__ == "__main__":
    main()
