from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.backtest_execution_v2 import run_backtest
from src.elastic_net_transversal import FEATURES, ElasticNetConfig
from src.features_weekly_1w import TARGET_1W
from src.trading_config import load_execution_profile

PANEL_PATH = Path("data/processed/features_weekly_1w.csv.gz")
OUTPUT_ROOT = Path("data/processed/execution_backtest")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backtest walk-forward à horizon et fréquence d'une semaine."
    )
    parser.add_argument("--profile", default="sans_stop")
    parser.add_argument("--panel", type=Path, default=PANEL_PATH)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    panel = pd.read_csv(args.panel, parse_dates=["date"])
    execution_config = load_execution_profile(args.profile)
    model_config = ElasticNetConfig(purge_weeks=1, test_every_n_weeks=1)
    periods, holdings = run_backtest(
        panel,
        FEATURES,
        execution_config,
        model_config,
        target_column=TARGET_1W,
        horizon_weeks=1,
    )
    if periods.empty:
        raise RuntimeError("Aucune période hebdomadaire n'a été produite.")

    output = args.output_root / f"v1_1w_{args.profile}"
    output.mkdir(parents=True, exist_ok=True)
    periods.to_csv(output / "periods.csv", index=False)
    holdings.to_csv(output / "holdings.csv", index=False)
    print(f"Résultats : {output}")
    print(f"Semaines : {len(periods)}")
    print(f"Surperformance nette moyenne : {periods['net_excess_1w'].mean():+.2%}")
    print(f"Taux de victoire : {periods['net_excess_1w'].gt(0).mean():.2%}")
    print(f"Turnover one-way moyen : {periods['one_way_turnover'].mean():.2%}")
    print(f"Coût moyen : {periods['total_cost_return'].mean():.3%}")


if __name__ == "__main__":
    main()
