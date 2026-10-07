from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


WEEKS_PER_YEAR = 52


def load_bloomberg_data(
    data_root: str | Path = "data/bloomberg/data",
):
    """
    Charge les exports Bloomberg nettoyés déjà présents dans le repo.
    """

    data_root = Path(data_root)

    prices = pd.read_csv(
        data_root / "prices_10y.csv.gz",
        index_col="date",
        parse_dates=True,
    )

    volumes = pd.read_csv(
        data_root / "volumes_10y.csv.gz",
        index_col="date",
        parse_dates=True,
    )

    benchmark = pd.read_csv(
        data_root / "benchmark_10y.csv",
        index_col="date",
        parse_dates=True,
    )["px_last"]

    return prices, volumes, benchmark


def to_weekly_prices(prices_daily: pd.DataFrame) -> pd.DataFrame:
    """
    Prend les prix quotidiens et garde le dernier prix disponible de chaque semaine.
    """

    prices_daily = prices_daily.sort_index()

    weekly_prices = prices_daily.resample("W-FRI").last()

    return weekly_prices


def to_weekly_volumes(volumes_daily: pd.DataFrame) -> pd.DataFrame:
    """
    Additionne les volumes échangés pendant chaque semaine.
    """

    volumes_daily = volumes_daily.sort_index()

    weekly_volumes = volumes_daily.resample("W-FRI").sum(min_count=1)

    return weekly_volumes


def to_weekly_benchmark(benchmark_daily: pd.Series) -> pd.Series:
    """
    Garde la dernière valeur disponible du WLS chaque semaine.
    """

    benchmark_daily = benchmark_daily.sort_index()

    weekly_benchmark = benchmark_daily.resample("W-FRI").last()

    return weekly_benchmark


def compute_features(
    weekly_prices: pd.DataFrame,
    weekly_volumes: pd.DataFrame,
):
    """
    Calcule les premières features historiques de notre modèle.
    """

    weekly_returns = weekly_prices.pct_change(fill_method=None)

    # Momentum 1 mois ≈ 4 semaines
    mom_1m = weekly_prices.pct_change(4, fill_method=None)

    # Momentum 3 mois ≈ 13 semaines
    mom_3m = weekly_prices.pct_change(13, fill_method=None)

    # Momentum 6 mois ≈ 26 semaines
    mom_6m = weekly_prices.pct_change(26, fill_method=None)

    # Volatilité annualisée sur les 13 dernières semaines
    volatility_13w = (
        weekly_returns
        .rolling(13, min_periods=13)
        .std()
        * np.sqrt(WEEKS_PER_YEAR)
    )

    # Volume anormal :
    # volume de la semaine / volume médian des 13 dernières semaines
    median_volume_13w = (
        weekly_volumes
        .rolling(13, min_periods=13)
        .median()
    )

    abnormal_volume_13w = weekly_volumes / median_volume_13w

    # Distance au plus haut des 52 dernières semaines
    rolling_high_52w = (
        weekly_prices
        .rolling(52, min_periods=52)
        .max()
    )

    distance_52w_high = weekly_prices / rolling_high_52w - 1

    return {
        "mom_1m": mom_1m,
        "mom_3m": mom_3m,
        "mom_6m": mom_6m,
        "volatility_13w": volatility_13w,
        "abnormal_volume_13w": abnormal_volume_13w,
        "distance_52w_high": distance_52w_high,
    }


def compute_target(
    weekly_prices: pd.DataFrame,
    weekly_benchmark: pd.Series,
    horizon_weeks: int = 5,
):
    """
    Calcule notre target :

    rendement futur de l'action sur 5 semaines
    moins
    rendement futur du WLS sur 5 semaines.
    """

    stock_future_return = (
        weekly_prices
        .pct_change(horizon_weeks, fill_method=None)
        .shift(-horizon_weeks)
    )

    benchmark_future_return = (
        weekly_benchmark
        .pct_change(horizon_weeks, fill_method=None)
        .shift(-horizon_weeks)
    )

    excess_return = stock_future_return.sub(
        benchmark_future_return,
        axis=0,
    )

    return excess_return


def cross_sectional_rank(feature: pd.DataFrame) -> pd.DataFrame:
    """
    Transforme chaque feature en rang percentile à chaque date.

    Exemple :
    0.95 = l'action est environ dans les 5 % meilleures
    pour cette variable à cette date.
    """

    return feature.rank(
        axis=1,
        pct=True,
        method="average",
    )


def build_panel(
    prices_daily: pd.DataFrame,
    volumes_daily: pd.DataFrame,
    benchmark_daily: pd.Series,
):
    """
    Construit le panel final :

    une ligne = une action à une date.
    """

    weekly_prices = to_weekly_prices(prices_daily)

    weekly_volumes = to_weekly_volumes(volumes_daily)

    weekly_benchmark = to_weekly_benchmark(benchmark_daily)

    # ============================================================
    # RETIRER LA SEMAINE EN COURS SI ELLE N'EST PAS TERMINÉE
    # ============================================================

    last_market_date = min(
        prices_daily.index.max(),
        volumes_daily.index.max(),
    )

    days_since_friday = (
        last_market_date.weekday() - 4
    ) % 7

    last_completed_friday = (
        last_market_date
        - pd.Timedelta(days=days_since_friday)
    )

    weekly_prices = weekly_prices.loc[
        weekly_prices.index <= last_completed_friday
    ]

    weekly_volumes = weekly_volumes.loc[
        weekly_volumes.index <= last_completed_friday
    ]

    weekly_benchmark = weekly_benchmark.loc[
        weekly_benchmark.index <= last_completed_friday
    ]

    # On aligne exactement les mêmes dates / actions
    weekly_volumes = weekly_volumes.reindex(
        index=weekly_prices.index,
        columns=weekly_prices.columns,
    )

    raw_features = compute_features(
        weekly_prices,
        weekly_volumes,
    )

    target = compute_target(
        weekly_prices,
        weekly_benchmark,
    )

    panel_parts = []

    for feature_name, feature_values in raw_features.items():

        # Valeur brute
        raw_long = (
            feature_values
            .stack()
            .rename(feature_name)
        )

        panel_parts.append(raw_long)

        # Rang transversal
        ranked = cross_sectional_rank(feature_values)

        ranked_long = (
            ranked
            .stack()
            .rename(f"{feature_name}_rank")
        )

        panel_parts.append(ranked_long)

    target_long = (
        target
        .stack()
        .rename("future_excess_return_5w")
    )

    panel_parts.append(target_long)

    panel = pd.concat(
        panel_parts,
        axis=1,
    )

    panel.index.names = [
        "date",
        "id",
    ]

    panel = panel.reset_index()

    return panel


if __name__ == "__main__":

    prices, volumes, benchmark = load_bloomberg_data()

    panel = build_panel(
        prices,
        volumes,
        benchmark,
    )

    output_path = Path(
        "data/processed/features_weekly_v1.csv.gz"
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    panel.to_csv(
        output_path,
        index=False,
        compression="gzip",
    )

    print(
        f"Fichier créé : {output_path}"
    )

    print(
        f"Nombre de lignes : {len(panel):,}"
    )

    print(panel.head())