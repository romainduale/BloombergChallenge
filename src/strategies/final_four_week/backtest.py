from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.backtest_execution_v2 import run_backtest
from src.elastic_net_transversal import FEATURES
from src.strategies.final_four_week.config import (
    DEFAULT_STRATEGY_PROFILE,
    StrategyProfile,
    load_strategy_profile,
)
from src.strategies.final_four_week.constants import HORIZON_WEEKS, PANEL_PATH, TARGET_4W
from src.strategies.final_four_week.features import create_panel
from src.strategies.final_four_week.models import four_week_model_config
from src.trading_config import load_execution_profile

OUTPUT_ROOT = Path("data/processed/execution_backtest")


def run_four_week_backtest(
    panel: pd.DataFrame,
    *,
    execution_profile: str = "sans_stop",
    strategy_profile: StrategyProfile | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    profile = strategy_profile or load_strategy_profile(DEFAULT_STRATEGY_PROFILE)
    return run_backtest(
        panel,
        FEATURES,
        load_execution_profile(execution_profile),
        four_week_model_config(),
        target_column=TARGET_4W,
        horizon_weeks=HORIZON_WEEKS,
        tail_weight=profile.tail_weight,
        elastic_weight=profile.elastic_weight,
        top_n=profile.top_n,
        shortlist_size=profile.shortlist_size,
        max_correlation=profile.max_correlation,
        kappa=profile.kappa,
        max_position_weight=profile.max_position_weight,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backtest walk-forward de la stratégie finale à quatre semaines."
    )
    parser.add_argument("--profile", dest="execution_profile", default="sans_stop")
    parser.add_argument(
        "--strategy-profile",
        choices=["prudent", "intermediaire", "agressif"],
        default=DEFAULT_STRATEGY_PROFILE,
    )
    parser.add_argument("--panel", type=Path, default=PANEL_PATH)
    parser.add_argument("--rebuild-features", action="store_true")
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.rebuild_features or not args.panel.exists():
        panel = create_panel(args.panel)
    else:
        panel = pd.read_csv(args.panel, parse_dates=["date"])
    strategy_profile = load_strategy_profile(args.strategy_profile)
    periods, holdings = run_four_week_backtest(
        panel,
        execution_profile=args.execution_profile,
        strategy_profile=strategy_profile,
    )
    if periods.empty:
        raise RuntimeError("Aucune période quatre semaines n'a été produite.")

    output = args.output_root / (f"final_4w_{args.strategy_profile}_{args.execution_profile}")
    output.mkdir(parents=True, exist_ok=True)
    periods.to_csv(output / "periods.csv", index=False)
    holdings.to_csv(output / "holdings.csv", index=False)
    metric = f"net_excess_{HORIZON_WEEKS}w"
    print(f"Résultats : {output}")
    print(f"Périodes : {len(periods)}")
    print(f"Surperformance nette moyenne : {periods[metric].mean():+.2%}")
    print(f"Taux de victoire : {periods[metric].gt(0).mean():.2%}")
    print(f"Turnover one-way moyen : {periods['one_way_turnover'].mean():.2%}")
    print(f"Coût moyen : {periods['total_cost_return'].mean():.3%}")


if __name__ == "__main__":
    main()
