from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from src.backtest_portfolio_v1 import make_elastic_model, make_tail_model
from src.elastic_net_transversal import (
    FEATURES as V1_FEATURES,
)
from src.elastic_net_transversal import (
    TARGET,
    ElasticNetConfig,
    calculate_rank_ic,
)
from src.features_v2 import OUTPUT_PATH as PANEL_V2_PATH
from src.features_v2 import V2_ADDITIONAL_FEATURES, V2_FEATURES
from src.tail_model_v1 import precision_at_top_decile

OUTPUT_DIR = Path("data/processed/feature_comparison_v2")


def get_test_dates(
    data: pd.DataFrame,
    config: ElasticNetConfig,
    offset: int,
) -> pd.DatetimeIndex:
    dates = pd.DatetimeIndex(sorted(pd.to_datetime(data["date"].unique())))
    first_test_date = (
        dates.min()
        + pd.DateOffset(years=config.train_years)
        + pd.Timedelta(weeks=config.purge_weeks)
    )
    return dates[dates >= first_test_date][offset :: config.test_every_n_weeks]


def _single_factor_prediction(
    train: pd.DataFrame,
    test: pd.DataFrame,
    feature: str,
) -> np.ndarray:
    x = train[feature].to_numpy(dtype=float)
    y = train[TARGET].to_numpy(dtype=float)
    x_centered = x - x.mean()
    denominator = float(x_centered @ x_centered)
    slope = 0.0 if denominator == 0 else float(x_centered @ (y - y.mean()) / denominator)
    return test[feature].to_numpy(dtype=float) * slope


def run_comparison(
    panel: pd.DataFrame,
    config: ElasticNetConfig | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    cfg = config or ElasticNetConfig()
    data = panel.dropna(subset=V2_FEATURES + [TARGET]).copy()
    data["date"] = pd.to_datetime(data["date"])
    threshold = data.groupby("date")[TARGET].transform(lambda values: values.quantile(0.90))
    data["tail_target"] = data[TARGET].ge(threshold).astype(int)

    model_rows = []
    factor_rows = []
    feature_sets = {
        "v1_common_sample": V1_FEATURES,
        "v1_plus_ivol": V1_FEATURES + ["ivol_26w_rank"],
        "v1_plus_eps_revision": V1_FEATURES + ["eps_revision_3m_rank"],
        "v1_plus_ivol_eps": V1_FEATURES + ["ivol_26w_rank", "eps_revision_3m_rank"],
        "v2": V2_FEATURES,
    }

    for offset in range(cfg.test_every_n_weeks):
        for test_date in get_test_dates(data, cfg, offset):
            train_end = test_date - pd.Timedelta(weeks=cfg.purge_weeks)
            train_start = train_end - pd.DateOffset(years=cfg.train_years)
            train = data[(data["date"] >= train_start) & (data["date"] < train_end)]
            test = data[data["date"] == test_date]
            if len(train) < cfg.min_train_rows or len(test) < cfg.min_test_rows:
                continue

            for name, features in feature_sets.items():
                elastic = make_elastic_model(cfg)
                tail = make_tail_model()
                elastic.fit(train[features], train[TARGET])
                tail.fit(train[features], train["tail_target"])

                elastic_prediction = elastic.predict(test[features])
                tail_probability = tail.predict_proba(test[features])[:, 1]
                elastic_rank = pd.Series(elastic_prediction, index=test.index).rank(pct=True)
                tail_rank = pd.Series(tail_probability, index=test.index).rank(pct=True)
                combined_score = 0.75 * tail_rank + 0.25 * elastic_rank

                model_rows.append(
                    {
                        "date": test_date,
                        "offset": offset,
                        "feature_set": name,
                        "n_train": len(train),
                        "n_test": len(test),
                        "elastic_ic": calculate_rank_ic(test[TARGET], elastic_prediction),
                        "combined_ic": calculate_rank_ic(test[TARGET], combined_score.to_numpy()),
                        "tail_auc": roc_auc_score(test["tail_target"], tail_probability),
                        "tail_average_precision": average_precision_score(
                            test["tail_target"],
                            tail_probability,
                        ),
                        "tail_precision_top_decile": precision_at_top_decile(
                            test["tail_target"],
                            tail_probability,
                        ),
                    }
                )

            for feature in V2_ADDITIONAL_FEATURES:
                prediction = _single_factor_prediction(train, test, feature)
                factor_rows.append(
                    {
                        "date": test_date,
                        "offset": offset,
                        "feature": feature,
                        "ic": calculate_rank_ic(test[TARGET], prediction),
                    }
                )

    return pd.DataFrame(model_rows), pd.DataFrame(factor_rows)


def summarize_comparison(results: pd.DataFrame) -> pd.DataFrame:
    metrics = [
        "elastic_ic",
        "combined_ic",
        "tail_auc",
        "tail_average_precision",
        "tail_precision_top_decile",
    ]
    rows = []
    for feature_set, group in results.groupby("feature_set"):
        row = {"feature_set": feature_set, "n_periods": len(group)}
        for metric in metrics:
            row[f"mean_{metric}"] = float(group[metric].mean())
            row[f"median_{metric}"] = float(group[metric].median())
            row[f"std_{metric}"] = float(group[metric].std())
        row["positive_elastic_ic_pct"] = float(group["elastic_ic"].gt(0).mean())
        row["positive_combined_ic_pct"] = float(group["combined_ic"].gt(0).mean())
        rows.append(row)
    return pd.DataFrame(rows)


def summarize_factors(results: pd.DataFrame) -> pd.DataFrame:
    return (
        results.groupby("feature")["ic"]
        .agg(n_periods="count", mean_ic="mean", median_ic="median", std_ic="std")
        .assign(positive_ic_pct=results.groupby("feature")["ic"].apply(lambda x: x.gt(0).mean()))
        .reset_index()
        .sort_values("mean_ic", ascending=False)
    )


def main() -> None:
    panel = pd.read_csv(PANEL_V2_PATH, parse_dates=["date"])
    results, factors = run_comparison(panel)
    if results.empty:
        raise RuntimeError("Aucune période comparable n'a été produite.")

    summary = summarize_comparison(results)
    factor_summary = summarize_factors(factors)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results.to_csv(OUTPUT_DIR / "comparison_by_date.csv", index=False)
    summary.to_csv(OUTPUT_DIR / "comparison_summary.csv", index=False)
    factors.to_csv(OUTPUT_DIR / "additional_factor_ic_by_date.csv", index=False)
    factor_summary.to_csv(OUTPUT_DIR / "additional_factor_ic_summary.csv", index=False)

    print("\nCOMPARAISON V1 / V2 SUR ÉCHANTILLON COMMUN")
    print(summary.to_string(index=False))
    print("\nFEATURES ADDITIONNELLES")
    print(factor_summary.to_string(index=False))


if __name__ == "__main__":
    main()
