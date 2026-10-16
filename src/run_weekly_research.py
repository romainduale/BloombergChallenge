from __future__ import annotations

import argparse
import subprocess
import sys


def run_step(module: str, *arguments: str) -> None:
    command = [sys.executable, "-m", module, *arguments]
    print("\n" + "=" * 72)
    print("ÉTAPE : " + " ".join(command))
    print("=" * 72)
    subprocess.run(command, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recalcule et compare les stratégies 1 semaine et 5 semaines."
    )
    parser.add_argument("--profile", default="sans_stop")
    parser.add_argument(
        "--reuse-five-week",
        action="store_true",
        help="Réutilise le backtest 5 semaines existant au lieu de le recalculer.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_step("src.features_weekly_1w")
    run_step("src.backtest_execution_1w", "--profile", args.profile)
    if not args.reuse_five_week:
        run_step("src.features")
        run_step("src.backtest_execution_v2", "--profile", args.profile)
    comparison_arguments = [
        "--weekly",
        f"data/processed/execution_backtest/v1_1w_{args.profile}/periods.csv",
        "--five-week",
        f"data/processed/execution_backtest/v1_{args.profile}/periods.csv",
    ]
    if args.profile != "sans_stop":
        comparison_arguments.extend(
            [
                "--output-dir",
                f"data/processed/execution_backtest/horizon_comparison/{args.profile}",
            ]
        )
    run_step("src.compare_backtest_horizons", *comparison_arguments)


if __name__ == "__main__":
    main()
