from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest_portfolio_v1 import (
    TOP_N,
    benchmark_future_return,
    build_shortlist,
    estimate_historical_risk,
    load_market_history,
    make_elastic_model,
    make_tail_model,
    optimise,
    prepare_data,
)
from src.elastic_net_transversal import (
    FEATURES,
    TARGET,
    ElasticNetConfig,
    load_panel,
)

OUTPUT_DIR = Path("data/processed/portfolio_backtest")


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

    eligible = dates[dates >= first_test_date]

    return eligible[offset :: config.test_every_n_weeks]


def run_offset(
    offset: int,
    data: pd.DataFrame,
    config: ElasticNetConfig,
    weekly_prices: pd.DataFrame,
    weekly_benchmark: pd.Series,
) -> pd.DataFrame:
    test_dates = get_test_dates(
        data,
        config,
        offset,
    )

    rows = []

    print("\n")
    print("=" * 72)
    print(f"OFFSET {offset} - {len(test_dates)} périodes")
    print("=" * 72)

    for number, test_date in enumerate(
        test_dates,
        start=1,
    ):
        train_end = test_date - pd.Timedelta(weeks=config.purge_weeks)

        train_start = train_end - pd.DateOffset(years=config.train_years)

        train = data[(data["date"] >= train_start) & (data["date"] < train_end)].copy()

        test = data[data["date"] == test_date].copy()

        if len(train) < config.min_train_rows:
            continue

        if len(test) < config.min_test_rows:
            continue

        elastic = make_elastic_model(config)

        tail = make_tail_model()

        elastic.fit(
            train[FEATURES],
            train[TARGET],
        )

        tail.fit(
            train[FEATURES],
            train["tail_target"],
        )

        test["elastic_prediction"] = elastic.predict(test[FEATURES])

        test["tail_score"] = tail.predict_proba(test[FEATURES])[:, 1]

        test["elastic_rank"] = test["elastic_prediction"].rank(pct=True)

        test["tail_rank"] = test["tail_score"].rank(pct=True)

        test["combined_score"] = 0.75 * test["tail_rank"] + 0.25 * test["elastic_rank"]

        ranking = (
            test.sort_values(
                "combined_score",
                ascending=False,
            )
            .head(TOP_N)
            .copy()
        )

        try:
            covariance = estimate_historical_risk(
                test_date,
                ranking["id"].tolist(),
                weekly_prices,
                weekly_benchmark,
            )
        except ValueError:
            continue

        shortlist = build_shortlist(
            ranking,
            covariance,
        )

        if len(shortlist) < 6:
            continue

        weights = optimise(
            shortlist,
            covariance,
        )

        realised_excess = shortlist[TARGET].to_numpy(dtype=float)

        robust_excess = float(weights @ realised_excess)

        equal_excess = float(realised_excess.mean())

        benchmark_return = benchmark_future_return(
            test_date,
            weekly_benchmark,
        )

        if np.isnan(benchmark_return):
            continue

        robust_return = benchmark_return + robust_excess

        equal_return = benchmark_return + equal_excess

        rows.append(
            {
                "offset": offset,
                "date": test_date,
                "robust_excess_5w": (robust_excess),
                "equal_excess_5w": (equal_excess),
                "robust_return_5w": (robust_return),
                "equal_return_5w": (equal_return),
                "benchmark_return_5w": (benchmark_return),
                "max_weight": float(weights.max()),
                "n_positions_gt_1pct": int(np.sum(weights >= 0.01)),
            }
        )

        if number == 1 or number % 10 == 0 or number == len(test_dates):
            print(
                f"[{number}/"
                f"{len(test_dates)}] "
                f"{test_date.date()} "
                f"| Robust="
                f"{robust_excess:+.2%} "
                f"| EW="
                f"{equal_excess:+.2%}"
            )

    return pd.DataFrame(rows)


def summarize(
    results: pd.DataFrame,
) -> pd.DataFrame:
    rows = []

    for offset, group in results.groupby("offset"):
        robust_wealth = (1.0 + group["robust_return_5w"]).cumprod()

        benchmark_wealth = (1.0 + group["benchmark_return_5w"]).cumprod()

        equal_wealth = (1.0 + group["equal_return_5w"]).cumprod()

        robust_relative = float(robust_wealth.iloc[-1] / benchmark_wealth.iloc[-1] - 1.0)

        equal_relative = float(equal_wealth.iloc[-1] / benchmark_wealth.iloc[-1] - 1.0)

        rows.append(
            {
                "offset": offset,
                "n_periods": len(group),
                "mean_robust_excess": (group["robust_excess_5w"].mean()),
                "median_robust_excess": (group["robust_excess_5w"].median()),
                "beat_wls_pct": (group["robust_excess_5w"].gt(0).mean()),
                "mean_equal_excess": (group["equal_excess_5w"].mean()),
                "robust_vs_equal": (
                    group["robust_excess_5w"].mean() - group["equal_excess_5w"].mean()
                ),
                "cumulative_robust_vs_wls": (robust_relative),
                "cumulative_equal_vs_wls": (equal_relative),
            }
        )

    return pd.DataFrame(rows)


def main():
    config = ElasticNetConfig()

    print("Chargement des données...")

    panel = load_panel()

    panel["date"] = pd.to_datetime(panel["date"])

    data = prepare_data(panel)

    (
        weekly_prices,
        weekly_benchmark,
    ) = load_market_history()

    all_results = []

    for offset in range(5):
        result = run_offset(
            offset,
            data,
            config,
            weekly_prices,
            weekly_benchmark,
        )

        all_results.append(result)

    results = pd.concat(
        all_results,
        ignore_index=True,
    )

    summary = summarize(results)

    print("\n")
    print("=" * 90)
    print("VALIDATION PORTEFEUILLE - 5 OFFSETS")
    print("=" * 90)

    print(summary.to_string(index=False))

    print("\n")
    print("=" * 90)
    print("GLOBAL")
    print("=" * 90)

    print(f"Surperformance moyenne 5w : {results['robust_excess_5w'].mean():+.2%}")

    print(f"Surperformance médiane 5w : {results['robust_excess_5w'].median():+.2%}")

    print(f"% périodes battant WLS : {results['robust_excess_5w'].gt(0).mean():.1%}")

    print(f"Equal Weight moyen : {results['equal_excess_5w'].mean():+.2%}")

    print(
        "Avantage moyen Robust vs EW : "
        f"{(results['robust_excess_5w'].mean() - results['equal_excess_5w'].mean()):+.2%}"
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    results.to_csv(
        OUTPUT_DIR / "portfolio_5_offsets_results.csv",
        index=False,
    )

    summary.to_csv(
        OUTPUT_DIR / "portfolio_5_offsets_summary.csv",
        index=False,
    )


if __name__ == "__main__":
    main()
