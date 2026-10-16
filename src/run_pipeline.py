from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run_step(module: str, *arguments: str) -> None:
    command = [sys.executable, "-m", module, *arguments]
    print("\n" + "=" * 72)
    print("ÉTAPE : " + " ".join(command))
    print("=" * 72)
    subprocess.run(command, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pipeline V1 jusqu'au plan d'exécution.")
    parser.add_argument(
        "--profile",
        default="sans_stop",
        help="Profil d'exécution; sans_stop reste le défaut tant que le stop n'est pas validé.",
    )
    parser.add_argument("--capital", type=float, default=1_000_000.0)
    parser.add_argument("--current-positions", type=Path)
    parser.add_argument(
        "--skip-features",
        action="store_true",
        help="Réutilise le panel déjà produit dans data/processed.",
    )
    parser.add_argument(
        "--refresh-market-data",
        action="store_true",
        help="Télécharge et contrôle les nouveaux prix/volumes Yahoo avant les features.",
    )
    parser.add_argument(
        "--refresh-end",
        type=str,
        help="Date de fin YYYY-MM-DD du rafraîchissement Yahoo (aujourd'hui par défaut).",
    )
    parser.add_argument(
        "--opportunistic",
        action="store_true",
        help="Alloue 80 pour cent à la stratégie 5 semaines et 20 pour cent à yfinance.",
    )
    parser.add_argument(
        "--skip-analysts",
        action="store_true",
        help="N'interroge pas les objectifs de cours Yahoo pour la poche opportuniste.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.refresh_market_data:
        refresh_arguments = ["--end", args.refresh_end] if args.refresh_end else []
        run_step("src.refresh_feature_market_data", *refresh_arguments)
    if not args.skip_features:
        run_step("src.features")
    run_step("src.combined_signal_v1")
    run_step("src.risk_screen_v1")
    run_step("src.robust_optimizer_v1")

    portfolio_path = "data/processed/portfolio/portfolio_robust_v1.csv"
    if args.opportunistic:
        opportunistic_arguments = ["--skip-analysts"] if args.skip_analysts else []
        run_step("src.opportunistic_model", *opportunistic_arguments)
        portfolio_path = "data/processed/opportunistic/allocation_80_20.csv"

    execution_arguments = [
        "--portfolio",
        portfolio_path,
        "--profile",
        args.profile,
        "--capital",
        str(args.capital),
    ]
    if args.current_positions is not None:
        execution_arguments.extend(["--current-positions", str(args.current_positions)])
    run_step("src.build_execution_plan", *execution_arguments)
    if args.opportunistic:
        run_step("src.export_clean_allocations", "--capital", str(args.capital))


if __name__ == "__main__":
    main()
