from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import ElasticNet
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


# ============================================================
# VARIABLES UTILISÉES PAR LE MODÈLE
# ============================================================

FEATURES = [
    "mom_1m_rank",
    "mom_3m_rank",
    "mom_6m_rank",
    "volatility_13w_rank",
    "abnormal_volume_13w_rank",
    "distance_52w_high_rank",
]

TARGET = "future_excess_return_5w"


@dataclass(frozen=True)
class ElasticNetConfig:
    """
    Paramètres de notre première version.

    Ces valeurs ne sont PAS encore les paramètres finaux.
    On les optimisera ensuite proprement avec le backtest.
    """

    # Nombre d'années utilisées pour entraîner chaque modèle
    train_years: int = 3

    # On retire les 5 semaines juste avant le test
    # afin d'éviter que les targets d'entraînement
    # utilisent de l'information appartenant à la période test.
    purge_weeks: int = 5

    # On teste une date toutes les 5 semaines.
    # C'est cohérent avec notre horizon de compétition.
    test_every_n_weeks: int = 5

    # Paramètres Elastic Net V1
    alpha: float = 0.0005
    l1_ratio: float = 0.5

    # Minimum d'observations nécessaires
    min_train_rows: int = 20_000
    min_test_rows: int = 50


def load_panel(
    path: str | Path = "data/processed/features_weekly_v1.csv.gz",
) -> pd.DataFrame:
    """
    Charge le panel créé par features.py.
    """

    df = pd.read_csv(
        path,
        parse_dates=["date"],
    )

    df = df.replace(
        [np.inf, -np.inf],
        np.nan,
    )

    return df


def prepare_training_data(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Pour entraîner Elastic Net, nous gardons uniquement
    les observations pour lesquelles :

    - toutes les features existent ;
    - le rendement futur à 5 semaines existe.
    """

    required_columns = FEATURES + [TARGET]

    clean = df.dropna(
        subset=required_columns
    ).copy()

    clean = clean.sort_values(
        ["date", "id"]
    ).reset_index(drop=True)

    return clean


def make_model(
    config: ElasticNetConfig,
) -> Pipeline:
    """
    Construit notre modèle.

    StandardScaler :
        met les variables sur une échelle comparable.

    ElasticNet :
        apprend les coefficients permettant de prédire
        le rendement relatif futur.
    """

    model = Pipeline(
        steps=[
            (
                "scaler",
                StandardScaler(),
            ),
            (
                "elastic_net",
                ElasticNet(
                    alpha=config.alpha,
                    l1_ratio=config.l1_ratio,
                    max_iter=10_000,
                ),
            ),
        ]
    )

    return model


def calculate_rank_ic(
    actual_returns: pd.Series,
    predictions: np.ndarray,
) -> float:
    """
    Calcule l'Information Coefficient (IC).

    On compare :

        classement prédit
                VS
        classement réellement observé

    avec la corrélation de Spearman.
    """

    prediction_series = pd.Series(
        predictions,
        index=actual_returns.index,
    )

    if actual_returns.nunique() < 2:
        return np.nan

    if prediction_series.nunique() < 2:
        return np.nan

    return actual_returns.corr(
        prediction_series,
        method="spearman",
    )


def walk_forward_backtest(
    df: pd.DataFrame,
    config: ElasticNetConfig | None = None,
):
    """
    Backtest walk-forward avec purge de 5 semaines.

    Exemple :

    TRAIN
    2020 -------------------- 2023

                             PURGE
                             5 semaines

                                    TEST
                                    ↓
                                  semaine t

    Puis on avance dans le temps.
    """

    cfg = config or ElasticNetConfig()

    data = prepare_training_data(df)

    dates = pd.Index(
        sorted(data["date"].unique())
    )

    # Il faut assez d'historique avant le premier test.
    first_test_date = (
        dates.min()
        + pd.DateOffset(years=cfg.train_years)
        + pd.Timedelta(weeks=cfg.purge_weeks)
    )

    eligible_test_dates = dates[
        dates >= first_test_date
    ]

    test_dates = eligible_test_dates[
        :: cfg.test_every_n_weeks
    ]

    predictions_list = []
    ic_results = []

    print(
        f"Nombre de dates de test : {len(test_dates)}"
    )

    for number, test_date in enumerate(
        test_dates,
        start=1,
    ):

        test_date = pd.Timestamp(test_date)

        # ----------------------------------------------------
        # PURGE
        # ----------------------------------------------------

        train_end = (
            test_date
            - pd.Timedelta(
                weeks=cfg.purge_weeks
            )
        )

        # Fenêtre glissante de 3 ans
        train_start = (
            train_end
            - pd.DateOffset(
                years=cfg.train_years
            )
        )

        train = data[
            (data["date"] >= train_start)
            & (data["date"] < train_end)
        ].copy()

        test = data[
            data["date"] == test_date
        ].copy()

        if len(train) < cfg.min_train_rows:
            continue

        if len(test) < cfg.min_test_rows:
            continue

        # ----------------------------------------------------
        # X = VARIABLES EXPLICATIVES
        # y = CE QU'ON CHERCHE À PRÉDIRE
        # ----------------------------------------------------

        X_train = train[FEATURES]
        y_train = train[TARGET]

        X_test = test[FEATURES]
        y_test = test[TARGET]

        # ----------------------------------------------------
        # APPRENTISSAGE
        # ----------------------------------------------------

        model = make_model(cfg)

        model.fit(
            X_train,
            y_train,
        )

        # ----------------------------------------------------
        # PRÉDICTION
        # ----------------------------------------------------

        predictions = model.predict(
            X_test
        )

        test["predicted_excess_return"] = (
            predictions
        )

        # Classement prédit des actions
        test["predicted_rank"] = (
            test["predicted_excess_return"]
            .rank(
                pct=True,
                method="average",
            )
        )

        # ----------------------------------------------------
        # INFORMATION COEFFICIENT
        # ----------------------------------------------------

        ic = calculate_rank_ic(
            y_test,
            predictions,
        )

        ic_results.append(
            {
                "date": test_date,
                "ic": ic,
                "n_stocks": len(test),
                "n_train": len(train),
            }
        )

        predictions_list.append(
            test[
                [
                    "date",
                    "id",
                    TARGET,
                    "predicted_excess_return",
                    "predicted_rank",
                ]
            ]
        )

        print(
            f"[{number}/{len(test_dates)}] "
            f"{test_date.date()} "
            f"| train={len(train):,} "
            f"| test={len(test):,} "
            f"| IC={ic:.4f}"
        )

    if not predictions_list:
        raise ValueError(
            "Aucune prédiction n'a été produite."
        )

    predictions_df = pd.concat(
        predictions_list,
        ignore_index=True,
    )

    ic_df = pd.DataFrame(
        ic_results
    )

    return predictions_df, ic_df


def print_summary(
    ic_df: pd.DataFrame,
):
    """
    Résume les performances du signal.
    """

    valid_ic = ic_df["ic"].dropna()

    print("\n")
    print("=" * 60)
    print("RÉSULTATS ELASTIC NET V1")
    print("=" * 60)

    print(
        f"Nombre de périodes : "
        f"{len(valid_ic)}"
    )

    print(
        f"IC moyen : "
        f"{valid_ic.mean():.4f}"
    )

    print(
        f"IC médian : "
        f"{valid_ic.median():.4f}"
    )

    print(
        f"% périodes IC positif : "
        f"{(valid_ic > 0).mean():.1%}"
    )

    print(
        f"Écart-type IC : "
        f"{valid_ic.std():.4f}"
    )


def fit_latest_ranking(
    full_df: pd.DataFrame,
    config: ElasticNetConfig | None = None,
) -> pd.DataFrame:
    """
    Entraîne le modèle avec le passé puis produit
    le classement le plus récent disponible.

    Pour la date la plus récente, nous n'avons évidemment
    pas encore le rendement futur : ce n'est pas nécessaire
    pour faire une prédiction.
    """

    cfg = config or ElasticNetConfig()

    feature_data = full_df.dropna(
        subset=FEATURES
    ).copy()

    latest_date = feature_data[
        "date"
    ].max()

    latest = feature_data[
        feature_data["date"] == latest_date
    ].copy()

    # Pour entraîner le modèle, la target doit être connue.
    historical = full_df.dropna(
        subset=FEATURES + [TARGET]
    ).copy()

    train_end = (
        latest_date
        - pd.Timedelta(
            weeks=cfg.purge_weeks
        )
    )

    train_start = (
        train_end
        - pd.DateOffset(
            years=cfg.train_years
        )
    )

    train = historical[
        (historical["date"] >= train_start)
        & (historical["date"] < train_end)
    ].copy()

    model = make_model(cfg)

    model.fit(
        train[FEATURES],
        train[TARGET],
    )

    latest["predicted_excess_return"] = (
        model.predict(
            latest[FEATURES]
        )
    )

    latest["predicted_rank"] = (
        latest["predicted_excess_return"]
        .rank(
            ascending=True,
            pct=True,
        )
    )

    ranking = latest.sort_values(
        "predicted_excess_return",
        ascending=False,
    )

    return ranking[
        [
            "date",
            "id",
            "predicted_excess_return",
            "predicted_rank",
        ]
    ]


if __name__ == "__main__":

    config = ElasticNetConfig()

    print(
        "Chargement du panel..."
    )

    df = load_panel()

    print(
        f"{len(df):,} observations chargées."
    )

    print(
        "\nLancement du walk-forward..."
    )

    predictions, ic_results = (
        walk_forward_backtest(
            df,
            config=config,
        )
    )

    print_summary(
        ic_results
    )

    output_dir = Path(
        "data/processed"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    predictions.to_csv(
        output_dir
        / "elastic_net_predictions_v1.csv.gz",
        index=False,
        compression="gzip",
    )

    ic_results.to_csv(
        output_dir
        / "elastic_net_ic_v1.csv",
        index=False,
    )

    # --------------------------------------------------------
    # CLASSEMENT LE PLUS RÉCENT
    # --------------------------------------------------------

    latest_ranking = fit_latest_ranking(
        df,
        config=config,
    )

    latest_ranking.to_csv(
        output_dir
        / "latest_elastic_net_ranking_v1.csv",
        index=False,
    )

    print("\n")
    print("=" * 60)
    print("TOP 20 ELASTIC NET")
    print("=" * 60)

    print(
        latest_ranking.head(20)
    )