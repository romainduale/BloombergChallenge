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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.skip_features:
        run_step("src.features")
    run_step("src.combined_signal_v1")
    run_step("src.risk_screen_v1")
    run_step("src.robust_optimizer_v1")

    execution_arguments = [
        "--profile",
        args.profile,
        "--capital",
        str(args.capital),
    ]
    if args.current_positions is not None:
        execution_arguments.extend(["--current-positions", str(args.current_positions)])
    run_step("src.build_execution_plan", *execution_arguments)


if __name__ == "__main__":
    main()
