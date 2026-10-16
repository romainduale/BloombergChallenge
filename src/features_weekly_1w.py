from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.features import (
    build_panel,
    compute_target,
    load_bloomberg_data,
    to_weekly_benchmark,
    to_weekly_prices,
)

TARGET_1W = "future_excess_return_1w"
OUTPUT_PATH = Path("data/processed/features_weekly_1w.csv.gz")


def build_panel_1w(
    prices_daily: pd.DataFrame,
    volumes_daily: pd.DataFrame,
    benchmark_daily: pd.Series,
) -> pd.DataFrame:
    """Construit les features V1 avec une target relative future à une semaine."""

    panel = build_panel(prices_daily, volumes_daily, benchmark_daily).drop(
        columns=["future_excess_return_5w"]
    )
    weekly_prices = to_weekly_prices(prices_daily)
    weekly_benchmark = to_weekly_benchmark(benchmark_daily).reindex(weekly_prices.index)
    last_market_date = min(prices_daily.index.max(), volumes_daily.index.max())
    days_since_friday = (last_market_date.weekday() - 4) % 7
    last_completed_friday = last_market_date - pd.Timedelta(days=days_since_friday)
    weekly_prices = weekly_prices.loc[weekly_prices.index <= last_completed_friday]
    weekly_benchmark = weekly_benchmark.loc[weekly_benchmark.index <= last_completed_friday]
    target = compute_target(weekly_prices, weekly_benchmark, horizon_weeks=1)
    target_long = target.stack().rename(TARGET_1W).reset_index()
    target_long.columns = ["date", "id", TARGET_1W]

    return panel.merge(target_long, on=["date", "id"], how="left", validate="one_to_one")


def main() -> None:
    prices, volumes, benchmark = load_bloomberg_data()
    panel = build_panel_1w(prices, volumes, benchmark)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(OUTPUT_PATH, index=False, compression="gzip")
    print(f"Fichier créé : {OUTPUT_PATH}")
    print(f"Observations : {len(panel):,}")
    print(f"Targets 1 semaine disponibles : {panel[TARGET_1W].notna().sum():,}")


if __name__ == "__main__":
    main()
