from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.elastic_net_transversal import FEATURES as V1_FEATURES
from src.features import (
    build_panel,
    cross_sectional_rank,
    load_bloomberg_data,
    to_weekly_benchmark,
    to_weekly_prices,
)

EPS_HISTORY_PATH = Path("data/eps_history_5y.csv.gz")
OUTPUT_PATH = Path("data/processed/features_weekly_v2.csv.gz")

V2_ADDITIONAL_FEATURES = [
    "sortino_52w_rank",
    "eps_revision_3m_rank",
    "residual_momentum_26w_rank",
    "fip_26w_rank",
    "ivol_26w_rank",
    "amihud_13w_rank",
]

# Le 52-week high du fichier fourni est déjà représenté par
# distance_52w_high_rank dans la V1. L'ajouter une seconde fois ne ferait que
# dupliquer exactement le même classement transversal.
V2_FEATURES = V1_FEATURES + V2_ADDITIONAL_FEATURES


def compute_sortino(
    weekly_returns: pd.DataFrame,
    *,
    window: int = 52,
    min_periods: int = 40,
) -> pd.DataFrame:
    downside = weekly_returns.clip(upper=0.0)
    downside_deviation = downside.pow(2).rolling(window, min_periods=min_periods).mean().pow(0.5)
    sortino = (
        weekly_returns.rolling(window, min_periods=min_periods)
        .mean()
        .div(downside_deviation.replace(0.0, np.nan))
    )
    return sortino.replace([np.inf, -np.inf], np.nan)


def compute_residual_features(
    weekly_returns: pd.DataFrame,
    benchmark_returns: pd.Series,
    *,
    regression_window: int = 52,
    signal_window: int = 26,
    min_regression_periods: int = 40,
    min_signal_periods: int = 20,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    benchmark = benchmark_returns.reindex(weekly_returns.index)
    stock_mean = weekly_returns.rolling(
        regression_window,
        min_periods=min_regression_periods,
    ).mean()
    benchmark_mean = benchmark.rolling(
        regression_window,
        min_periods=min_regression_periods,
    ).mean()
    mean_product = (
        weekly_returns.mul(benchmark, axis=0)
        .rolling(
            regression_window,
            min_periods=min_regression_periods,
        )
        .mean()
    )
    covariance = mean_product.sub(stock_mean.mul(benchmark_mean, axis=0))
    benchmark_variance = (
        benchmark.pow(2)
        .rolling(regression_window, min_periods=min_regression_periods)
        .mean()
        .sub(benchmark_mean.pow(2))
    )
    beta = covariance.div(benchmark_variance.replace(0.0, np.nan), axis=0)
    alpha = stock_mean.sub(beta.mul(benchmark_mean, axis=0))
    residual = weekly_returns.sub(alpha).sub(beta.mul(benchmark, axis=0))

    residual_volatility = residual.rolling(
        signal_window,
        min_periods=min_signal_periods,
    ).std()
    residual_momentum = (
        residual.rolling(
            signal_window,
            min_periods=min_signal_periods,
        )
        .sum()
        .div(residual_volatility.replace(0.0, np.nan))
    )
    ivol = residual_volatility * np.sqrt(52.0)
    return (
        residual_momentum.replace([np.inf, -np.inf], np.nan),
        ivol.replace([np.inf, -np.inf], np.nan),
    )


def compute_fip(
    prices_daily: pd.DataFrame,
    weekly_index: pd.DatetimeIndex,
    *,
    calendar_window_days: int = 182,
    min_observations: int = 80,
) -> pd.DataFrame:
    daily_returns = prices_daily.sort_index().pct_change(fill_method=None)
    positive = daily_returns.gt(0).astype(float).where(daily_returns.notna())
    negative = daily_returns.lt(0).astype(float).where(daily_returns.notna())
    valid = daily_returns.notna().astype(float).where(daily_returns.notna())

    positive_count = positive.rolling(
        pd.Timedelta(days=calendar_window_days),
        min_periods=min_observations,
    ).sum()
    negative_count = negative.rolling(
        pd.Timedelta(days=calendar_window_days),
        min_periods=min_observations,
    ).sum()
    valid_count = valid.rolling(
        pd.Timedelta(days=calendar_window_days),
        min_periods=min_observations,
    ).sum()

    fip_daily = (positive_count - negative_count).div(valid_count.replace(0.0, np.nan))
    return fip_daily.resample("W-FRI").last().reindex(weekly_index)


def compute_amihud(
    prices_daily: pd.DataFrame,
    volumes_daily: pd.DataFrame,
    weekly_index: pd.DatetimeIndex,
    *,
    calendar_window_days: int = 91,
    min_observations: int = 40,
) -> pd.DataFrame:
    prices = prices_daily.sort_index()
    volumes = volumes_daily.reindex(index=prices.index, columns=prices.columns)
    daily_returns = prices.pct_change(fill_method=None)
    traded_amount = prices * volumes
    daily_illiquidity = daily_returns.abs().div(traded_amount.replace(0.0, np.nan))
    amihud_daily = daily_illiquidity.rolling(
        pd.Timedelta(days=calendar_window_days),
        min_periods=min_observations,
    ).mean()
    return amihud_daily.resample("W-FRI").last().reindex(weekly_index)


def compute_eps_revision(
    weekly_index: pd.DatetimeIndex,
    assets: pd.Index,
    *,
    path: str | Path = EPS_HISTORY_PATH,
    revision_months: int = 3,
    availability_lag_months: int = 1,
) -> pd.DataFrame:
    eps = pd.read_csv(path, index_col="month")
    eps = eps.reindex(columns=assets)
    denominator = eps.shift(revision_months).abs().replace(0.0, np.nan)
    revision = eps.sub(eps.shift(revision_months)).div(denominator)

    periods = pd.PeriodIndex(revision.index.astype(str), freq="M")
    revision.index = (periods + availability_lag_months).to_timestamp(how="end").normalize()
    expanded_index = revision.index.union(weekly_index).sort_values()
    weekly_revision = revision.reindex(expanded_index).ffill().reindex(weekly_index)
    return weekly_revision.replace([np.inf, -np.inf], np.nan)


def compute_additional_features(
    prices_daily: pd.DataFrame,
    volumes_daily: pd.DataFrame,
    benchmark_daily: pd.Series,
    *,
    eps_history_path: str | Path = EPS_HISTORY_PATH,
) -> dict[str, pd.DataFrame]:
    weekly_prices = to_weekly_prices(prices_daily)
    weekly_benchmark = to_weekly_benchmark(benchmark_daily).reindex(weekly_prices.index)
    weekly_returns = weekly_prices.pct_change(fill_method=None)
    benchmark_returns = weekly_benchmark.pct_change(fill_method=None)

    residual_momentum, ivol = compute_residual_features(
        weekly_returns,
        benchmark_returns,
    )

    return {
        "sortino_52w": compute_sortino(weekly_returns),
        "eps_revision_3m": compute_eps_revision(
            weekly_prices.index,
            weekly_prices.columns,
            path=eps_history_path,
        ),
        "residual_momentum_26w": residual_momentum,
        "fip_26w": compute_fip(prices_daily, weekly_prices.index),
        "ivol_26w": ivol,
        "amihud_13w": compute_amihud(
            prices_daily,
            volumes_daily,
            weekly_prices.index,
        ),
    }


def build_panel_v2(
    prices_daily: pd.DataFrame,
    volumes_daily: pd.DataFrame,
    benchmark_daily: pd.Series,
    *,
    eps_history_path: str | Path = EPS_HISTORY_PATH,
) -> pd.DataFrame:
    base_panel = build_panel(prices_daily, volumes_daily, benchmark_daily)
    additional = compute_additional_features(
        prices_daily,
        volumes_daily,
        benchmark_daily,
        eps_history_path=eps_history_path,
    )

    parts = []
    for name, values in additional.items():
        ranked = cross_sectional_rank(values)
        long_values = ranked.stack().rename(f"{name}_rank")
        parts.append(long_values)

    additional_panel = pd.concat(parts, axis=1)
    additional_panel.index.names = ["date", "id"]
    additional_panel = additional_panel.reset_index()

    return base_panel.merge(
        additional_panel,
        on=["date", "id"],
        how="left",
        validate="one_to_one",
    )


def main() -> None:
    prices, volumes, benchmark = load_bloomberg_data()
    panel = build_panel_v2(prices, volumes, benchmark)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(OUTPUT_PATH, index=False, compression="gzip")

    complete_v1 = int(panel[V1_FEATURES].notna().all(axis=1).sum())
    complete_v2 = int(panel[V2_FEATURES].notna().all(axis=1).sum())
    print(f"Fichier créé : {OUTPUT_PATH}")
    print(f"Observations : {len(panel):,}")
    print(f"Observations complètes V1 : {complete_v1:,}")
    print(f"Observations complètes V2 : {complete_v2:,}")


if __name__ == "__main__":
    main()
