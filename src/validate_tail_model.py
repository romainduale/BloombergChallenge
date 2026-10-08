from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    roc_auc_score,
)

from src.elastic_net_transversal import (
    ElasticNetConfig,
    load_panel,
)
from src.tail_model_v1 import (
    FEATURES,
    TARGET,
    make_tail_model,
    precision_at_top_decile,
    prepare_tail_data,
)

OUTPUT_DIR = Path("data/processed/tail_validation")


def get_test_dates(
    data: pd.DataFrame,
    config: ElasticNetConfig,
    offset: int,
) -> pd.DatetimeIndex:
    dates = pd.DatetimeIndex(sorted(data["date"].unique()))

    first_test_date = (
        dates.min()
        + pd.DateOffset(years=config.train_years)
        + pd.Timedelta(weeks=config.purge_weeks)
    )

    eligible_dates = dates[dates >= first_test_date]

    return eligible_dates[offset :: config.test_every_n_weeks]


def run_offset(
    data: pd.DataFrame,
    config: ElasticNetConfig,
    offset: int,
) -> pd.DataFrame:
    test_dates = get_test_dates(
        data,
        config,
        offset,
    )

    rows = []

    print(f"\nOffset {offset} | {len(test_dates)} dates")

    for number, test_date in enumerate(
        test_dates,
        start=1,
    ):
        train_end = test_date - pd.Timedelta(weeks=config.purge_weeks)

        train_start = train_end - pd.DateOffset(years=config.train_years)

        train = data[(data["date"] >= train_start) & (data["date"] < train_end)]

        test = data[data["date"] == test_date]

        if len(train) < config.min_train_rows:
            continue

        if len(test) < config.min_test_rows:
            continue

        model = make_tail_model()

        model.fit(
            train[FEATURES],
            train["tail_target"],
        )

        probabilities = model.predict_proba(test[FEATURES])[:, 1]

        y_true = test["tail_target"]

        auc = roc_auc_score(
            y_true,
            probabilities,
        )

        average_precision = average_precision_score(
            y_true,
            probabilities,
        )

        precision_top_10 = precision_at_top_decile(
            y_true,
            probabilities,
        )

        n_top = max(
            1,
            int(np.ceil(len(test) * 0.10)),
        )

        top_indices = np.argsort(probabilities)[-n_top:]

        mean_excess_top_10 = float(test.iloc[top_indices][TARGET].mean())

        rows.append(
            {
                "date": test_date,
                "offset": offset,
                "auc": auc,
                "average_precision": (average_precision),
                "precision_top_10": (precision_top_10),
                "mean_excess_return_top_10": (mean_excess_top_10),
                "n_test": len(test),
            }
        )

        if number == 1 or number % 10 == 0 or number == len(test_dates):
            print(
                f"[{number}/{len(test_dates)}] "
                f"{test_date.date()} "
                f"| AUC={auc:.3f} "
                f"| P@10={precision_top_10:.3f}"
            )

    return pd.DataFrame(rows)


def summarize_offsets(
    results: pd.DataFrame,
) -> pd.DataFrame:
    summary = (
        results.groupby("offset")
        .agg(
            n_periods=(
                "auc",
                "count",
            ),
            mean_auc=(
                "auc",
                "mean",
            ),
            mean_average_precision=(
                "average_precision",
                "mean",
            ),
            mean_precision_top_10=(
                "precision_top_10",
                "mean",
            ),
            mean_excess_return_top_10=(
                "mean_excess_return_top_10",
                "mean",
            ),
        )
        .reset_index()
    )

    return summary


def main():
    config = ElasticNetConfig()

    print("Chargement du panel...")

    raw_df = load_panel()

    data = prepare_tail_data(raw_df)

    print(f"{len(data):,} observations complètes utilisables.")

    all_results = []

    print("\n")
    print("=" * 60)
    print("TAIL MODEL - TEST DES 5 DÉCALAGES")
    print("=" * 60)

    for offset in range(config.test_every_n_weeks):
        offset_results = run_offset(
            data,
            config,
            offset,
        )

        all_results.append(offset_results)

    results = pd.concat(
        all_results,
        ignore_index=True,
    )

    summary = summarize_offsets(results)

    print("\n")
    print("=" * 60)
    print("RÉSULTATS TAIL - 5 DÉCALAGES")
    print("=" * 60)

    print(summary.to_string(index=False))

    print("\n")
    print("=" * 60)
    print("RÉSULTAT GLOBAL")
    print("=" * 60)

    print(f"AUC moyenne : {results['auc'].mean():.3f}")

    print(f"Average Precision moyenne : {results['average_precision'].mean():.3f}")

    print(f"Precision@10 moyenne : {results['precision_top_10'].mean():.3f}")

    print("Baseline aléatoire P@10 : 0.100")

    print(
        "Rendement relatif moyen du "
        "top 10 % prédit : "
        f"{results['mean_excess_return_top_10'].mean():.2%}"
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    results.to_csv(
        OUTPUT_DIR / "tail_offsets_results.csv",
        index=False,
    )

    summary.to_csv(
        OUTPUT_DIR / "tail_offsets_summary.csv",
        index=False,
    )


if __name__ == "__main__":
    main()
