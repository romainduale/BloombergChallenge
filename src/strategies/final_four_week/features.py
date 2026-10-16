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
from src.strategies.final_four_week.constants import PANEL_PATH, TARGET_4W


def build_panel_4w(
    prices_daily: pd.DataFrame,
    volumes_daily: pd.DataFrame,
    benchmark_daily: pd.Series,
) -> pd.DataFrame:
    """Construit les features V1 avec une cible relative future à quatre semaines."""

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

    target = compute_target(weekly_prices, weekly_benchmark, horizon_weeks=4)
    target_long = target.stack().rename(TARGET_4W).reset_index()
    target_long.columns = ["date", "id", TARGET_4W]
    return panel.merge(target_long, on=["date", "id"], how="left", validate="one_to_one")


def create_panel(output_path: Path = PANEL_PATH) -> pd.DataFrame:
    prices, volumes, benchmark = load_bloomberg_data()
    panel = build_panel_4w(prices, volumes, benchmark)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(output_path, index=False, compression="gzip")
    return panel


def main() -> None:
    panel = create_panel()
    print(f"Fichier créé : {PANEL_PATH}")
    print(f"Observations : {len(panel):,}")
    print(f"Targets 4 semaines disponibles : {panel[TARGET_4W].notna().sum():,}")
    print(f"Dernier signal disponible : {panel['date'].max().date()}")


if __name__ == "__main__":
    main()
