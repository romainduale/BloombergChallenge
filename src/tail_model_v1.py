from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import (
    LogisticRegression,
)
from sklearn.metrics import (
    average_precision_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import (
    StandardScaler,
)

from src.elastic_net_transversal import (
    FEATURES,
    TARGET,
    ElasticNetConfig,
    load_panel,
)

OUTPUT_DIR = Path("data/processed/tail_model")

TAIL_QUANTILE = 0.90


def prepare_tail_data(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Crée notre cible Tail.

    tail_target = 1 :
        action dans les 10 % meilleures
        performances relatives futures
        à 5 semaines.

    tail_target = 0 :
        sinon.
    """

    data = (
        df.dropna(subset=FEATURES + [TARGET])
        .copy()
        .sort_values(["date", "id"])
        .reset_index(drop=True)
    )

    threshold = data.groupby("date")[TARGET].transform(lambda s: s.quantile(TAIL_QUANTILE))

    data["tail_target"] = (data[TARGET] >= threshold).astype(int)

    return data


def make_tail_model() -> Pipeline:
    """
    Régression logistique :

    elle renvoie une probabilité
    d'appartenir au top 10 % futur.
    """

    return Pipeline(
        steps=[
            (
                "scaler",
                StandardScaler(),
            ),
            (
                "logistic",
                LogisticRegression(
                    C=1.0,
                    solver="lbfgs",
                    max_iter=1000,
                    class_weight=("balanced"),
                    l1_ratio=0.0,
                ),
            ),
        ]
    )


def precision_at_top_decile(
    y_true: pd.Series,
    probabilities: np.ndarray,
) -> float:
    """
    Parmi les 10 % d'actions
    que notre modèle préfère,
    combien finissent réellement
    dans le top 10 % ?

    Au hasard :
        environ 10 %.
    """

    n_top = max(
        1,
        int(np.ceil(len(probabilities) * 0.10)),
    )

    top_indices = np.argsort(probabilities)[-n_top:]

    return float(y_true.iloc[top_indices].mean())


def walk_forward_tail(
    data: pd.DataFrame,
    config: ElasticNetConfig,
) -> pd.DataFrame:
    """
    Backtest walk-forward du modèle Tail.
    """

    dates = pd.DatetimeIndex(sorted(data["date"].unique()))

    first_test_date = (
        dates.min()
        + pd.DateOffset(years=config.train_years)
        + pd.Timedelta(weeks=config.purge_weeks)
    )

    eligible_dates = dates[dates >= first_test_date]

    test_dates = eligible_dates[:: config.test_every_n_weeks]

    rows = []

    print("\n" + "=" * 60)
    print("BACKTEST TAIL MODEL V1")
    print("=" * 60)

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

        top_count = max(
            1,
            int(np.ceil(len(test) * 0.10)),
        )

        top_indices = np.argsort(probabilities)[-top_count:]

        mean_excess_top_10 = float(test.iloc[top_indices][TARGET].mean())

        rows.append(
            {
                "date": test_date,
                "auc": auc,
                "average_precision": (average_precision),
                "precision_top_10": (precision_top_10),
                "mean_excess_return_top_10": (mean_excess_top_10),
                "n_test": len(test),
            }
        )

        if number == 1 or number % 10 == 0 or number == len(test_dates):
            print(
                f"[{number}/"
                f"{len(test_dates)}] "
                f"{test_date.date()} "
                f"| AUC={auc:.3f} "
                f"| P@10="
                f"{precision_top_10:.3f}"
            )

    return pd.DataFrame(rows)


def fit_latest_tail_ranking(
    full_df: pd.DataFrame,
    config: ElasticNetConfig,
) -> pd.DataFrame:
    """
    Produit le classement actuel
    des actions ayant le plus fort
    potentiel Tail.
    """

    latest_features = full_df.dropna(subset=FEATURES).copy()

    latest_date = latest_features["date"].max()

    latest = latest_features[latest_features["date"] == latest_date].copy()

    historical = prepare_tail_data(full_df)

    train_end = latest_date - pd.Timedelta(weeks=config.purge_weeks)

    train_start = train_end - pd.DateOffset(years=config.train_years)

    train = historical[(historical["date"] >= train_start) & (historical["date"] < train_end)]

    model = make_tail_model()

    model.fit(
        train[FEATURES],
        train["tail_target"],
    )

    latest["tail_probability"] = model.predict_proba(latest[FEATURES])[:, 1]

    latest["tail_rank"] = latest["tail_probability"].rank(
        pct=True,
        method="average",
    )

    ranking = latest.sort_values(
        "tail_probability",
        ascending=False,
    )

    return ranking[
        [
            "date",
            "id",
            "tail_probability",
            "tail_rank",
        ]
    ]


def print_summary(
    results: pd.DataFrame,
) -> None:
    print("\n")
    print("=" * 60)
    print("RÉSULTATS TAIL MODEL V1")
    print("=" * 60)

    print(f"Nombre de périodes : {len(results)}")

    print(f"AUC moyenne : {results['auc'].mean():.3f}")

    print(f"Average Precision moyenne : {results['average_precision'].mean():.3f}")

    print(f"Precision@10 % moyenne : {results['precision_top_10'].mean():.3f}")

    print("Baseline aléatoire Precision@10 % : 0.100")

    print(
        "Rendement relatif futur moyen "
        "du top 10 % prédit : "
        f"{results['mean_excess_return_top_10'].mean():.2%}"
    )


def main():
    config = ElasticNetConfig()

    print("Chargement du panel...")

    raw_df = load_panel()

    tail_data = prepare_tail_data(raw_df)

    print(f"{len(tail_data):,} observations complètes utilisables.")

    results = walk_forward_tail(
        tail_data,
        config,
    )

    print_summary(results)

    latest_ranking = fit_latest_tail_ranking(
        raw_df,
        config,
    )

    print("\n")
    print("=" * 60)
    print("TOP 20 TAIL MODEL")
    print("=" * 60)

    print(latest_ranking.head(20))

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    results.to_csv(
        OUTPUT_DIR / "tail_backtest_v1.csv",
        index=False,
    )

    latest_ranking.to_csv(
        OUTPUT_DIR / "latest_tail_ranking_v1.csv",
        index=False,
    )


if __name__ == "__main__":
    main()
