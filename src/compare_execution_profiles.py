from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from src.audit_backtest import summarize_group

DEFAULT_PROFILES = ("sans_stop", "stop_fixe", "equilibre")


def summarize_profile(periods: pd.DataFrame, profile: str) -> dict[str, float | int | str]:
    by_offset = pd.DataFrame([summarize_group(group) for _, group in periods.groupby("offset")])
    return {
        "profile": profile,
        "n_periods": len(periods),
        "mean_net_excess_5w": float(periods["net_excess_5w"].mean()),
        "win_rate": float(periods["net_excess_5w"].gt(0).mean()),
        "mean_one_way_turnover": float(periods["one_way_turnover"].mean()),
        "mean_cost_return": float(periods["total_cost_return"].mean()),
        "mean_stops_per_period": float(periods["n_stops"].mean()),
        "mean_net_relative_return_by_offset": float(by_offset["net_relative_return"].mean()),
        "worst_max_drawdown_by_offset": float(by_offset["max_drawdown"].min()),
        "offset_relative_return_std": float(by_offset["net_relative_return"].std()),
        "mean_limit_fill_rate": float(periods["limit_fill_rate"].mean()),
    }


def compare_profiles(
    profile_periods: dict[str, pd.DataFrame],
    baseline: str = "sans_stop",
) -> pd.DataFrame:
    if baseline not in profile_periods:
        raise KeyError(f"Le profil de référence {baseline!r} est absent.")

    baseline_periods = profile_periods[baseline][["offset", "date", "net_return_5w"]].rename(
        columns={"net_return_5w": "baseline_net_return_5w"}
    )
    rows = []
    for profile, periods in profile_periods.items():
        summary = summarize_profile(periods, profile)
        matched = periods.merge(baseline_periods, on=["offset", "date"], how="inner")
        delta = matched["net_return_5w"] - matched["baseline_net_return_5w"]
        summary["matched_periods_vs_baseline"] = len(matched)
        summary["mean_net_return_delta_vs_baseline"] = float(delta.mean())
        summary["period_improvement_rate_vs_baseline"] = float(delta.gt(0).mean())
        rows.append(summary)

    result = pd.DataFrame(rows)
    return result.replace([np.inf, -np.inf], np.nan)


def render_markdown(frame: pd.DataFrame) -> str:
    header = "| " + " | ".join(frame.columns) + " |"
    separator = "| " + " | ".join(["---"] * len(frame.columns)) + " |"
    rows = []
    for values in frame.itertuples(index=False, name=None):
        cells = []
        for value in values:
            if pd.isna(value):
                cells.append("")
            elif isinstance(value, (float, np.floating)):
                cells.append(f"{float(value):.6g}")
            else:
                cells.append(str(value))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(["# Comparaison des règles de stop-loss", "", header, separator, *rows, ""])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare sans stop, stop fixe et stop lié à la volatilité."
    )
    parser.add_argument("--base-dir", type=Path, default=Path("data/processed/execution_backtest"))
    parser.add_argument("--feature-set", choices=["v1", "v2"], default="v1")
    parser.add_argument("--profiles", nargs="+", default=list(DEFAULT_PROFILES))
    parser.add_argument("--baseline", default="sans_stop")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/execution_backtest/profile_comparison"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    profile_periods = {}
    for profile in args.profiles:
        path = args.base_dir / f"{args.feature_set}_{profile}" / "periods.csv"
        profile_periods[profile] = pd.read_csv(path, parse_dates=["date", "end_date"])

    comparison = compare_profiles(profile_periods, baseline=args.baseline)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    comparison.to_csv(args.output_dir / "stop_loss_comparison.csv", index=False)
    (args.output_dir / "stop_loss_comparison.md").write_text(
        render_markdown(comparison),
        encoding="utf-8",
    )
    print(comparison.to_string(index=False))
    print(f"Comparaison créée dans {args.output_dir}")


if __name__ == "__main__":
    main()
