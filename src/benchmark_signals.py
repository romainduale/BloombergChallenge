from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.elastic_net_transversal import (
    FEATURES,
    TARGET,
    ElasticNetConfig,
    calculate_rank_ic,
    load_panel,
    make_model,
    prepare_training_data,
)

OUTPUT_DIR = Path("data/processed/benchmark")


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


def single_factor_slopes(
    train: pd.DataFrame,
) -> dict[str, float]:
    """
    Estime le sens de chaque facteur
    uniquement avec les données d'entraînement.

    slope > 0 :
        facteur élevé = plutôt favorable

    slope < 0 :
        facteur élevé = plutôt défavorable
    """

    x = train[FEATURES].to_numpy(dtype=float)

    y = train[TARGET].to_numpy(dtype=float)

    x_centered = x - x.mean(axis=0)

    y_centered = y - y.mean()

    numerator = x_centered.T @ y_centered

    denominator = np.sum(
        x_centered**2,
        axis=0,
    )

    slopes = np.divide(
        numerator,
        denominator,
        out=np.zeros_like(numerator),
        where=denominator > 0,
    )

    return dict(
        zip(
            FEATURES,
            slopes,
            strict=True,
        )
    )


def run_benchmark(
    data: pd.DataFrame,
    config: ElasticNetConfig,
) -> pd.DataFrame:
    rows = []

    print("\n" + "=" * 60)
    print("BENCHMARK ELASTIC NET VS FACTEURS SEULS")
    print("=" * 60)

    for offset in range(config.test_every_n_weeks):
        test_dates = get_test_dates(
            data,
            config,
            offset,
        )

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

            # =========================
            # ELASTIC NET
            # =========================

            model = make_model(config)

            model.fit(
                train[FEATURES],
                train[TARGET],
            )

            elastic_predictions = model.predict(test[FEATURES])

            elastic_ic = calculate_rank_ic(
                test[TARGET],
                elastic_predictions,
            )

            rows.append(
                {
                    "date": test_date,
                    "offset": offset,
                    "signal": "elastic_net",
                    "ic": elastic_ic,
                }
            )

            # =========================
            # FACTEURS INDIVIDUELS
            # =========================

            slopes = single_factor_slopes(train)

            for feature in FEATURES:
                predictions = test[feature].to_numpy() * slopes[feature]

                factor_ic = calculate_rank_ic(
                    test[TARGET],
                    predictions,
                )

                rows.append(
                    {
                        "date": test_date,
                        "offset": offset,
                        "signal": feature,
                        "ic": factor_ic,
                    }
                )

            if number == 1 or number % 10 == 0 or number == len(test_dates):
                print(
                    f"[{number}/"
                    f"{len(test_dates)}] "
                    f"{test_date.date()} "
                    f"| Elastic Net "
                    f"IC={elastic_ic:.4f}"
                )

    return pd.DataFrame(rows)


def summarize_results(
    results: pd.DataFrame,
) -> pd.DataFrame:
    summary = (
        results.groupby("signal")["ic"]
        .agg(
            n_periods="count",
            mean_ic="mean",
            median_ic="median",
            std_ic="std",
        )
        .reset_index()
    )

    positive_pct = (
        results.assign(positive=(results["ic"] > 0))
        .groupby("signal")["positive"]
        .mean()
        .rename("positive_ic_pct")
        .reset_index()
    )

    summary = summary.merge(
        positive_pct,
        on="signal",
        how="left",
    )

    return summary.sort_values(
        "mean_ic",
        ascending=False,
    ).reset_index(drop=True)


def main():
    config = ElasticNetConfig()

    print("Chargement du panel...")

    raw_df = load_panel()

    data = prepare_training_data(raw_df)

    print(f"{len(data):,} observations complètes utilisables.")

    results = run_benchmark(
        data,
        config,
    )

    summary = summarize_results(results)

    print("\n")
    print("=" * 60)
    print("RÉSULTAT FINAL DU BENCHMARK")
    print("=" * 60)

    print(summary.to_string(index=False))

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    results.to_csv(
        OUTPUT_DIR / "signal_benchmark_by_date.csv",
        index=False,
    )

    summary.to_csv(
        OUTPUT_DIR / "signal_benchmark_summary.csv",
        index=False,
    )


if __name__ == "__main__":
    main()
