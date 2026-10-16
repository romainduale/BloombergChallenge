from __future__ import annotations

from pathlib import Path

import pandas as pd

BASE = Path("data/processed/execution_backtest")
BENCHMARK_PATH = Path("data/bloomberg/data/benchmark_10y.csv")
FIVE_WEEK_PATH = BASE / "v1_sans_stop" / "periods.csv"
ONE_WEEK_PATH = BASE / "v1_1w_sans_stop" / "periods.csv"
COMPARISON_PATH = BASE / "horizon_comparison" / "comparison_summary.csv"


def require_file(path: Path, command: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Fichier manquant : {path}\nLance d'abord : {command}")


def load_periods(path: Path, horizon_weeks: int) -> pd.DataFrame:
    require_file(path, ".venv/bin/python -m src.run_weekly_research")
    frame = pd.read_csv(path, parse_dates=["date", "end_date"])
    return_column = f"net_return_{horizon_weeks}w"
    required = {"offset", "date", "end_date", return_column}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Colonnes manquantes dans {path} : {sorted(missing)}")
    frame[return_column] = pd.to_numeric(frame[return_column], errors="coerce")
    return frame.dropna(subset=[return_column]).copy()


def nav_paths(periods: pd.DataFrame, horizon_weeks: int) -> dict[int, pd.Series]:
    """Construit une NAV base 100 par trajectoire, datée à la fin de chaque période."""

    return_column = f"net_return_{horizon_weeks}w"
    paths: dict[int, pd.Series] = {}
    for offset, group in periods.groupby("offset"):
        ordered = group.sort_values("date")
        initial = pd.Series(
            [100.0],
            index=pd.DatetimeIndex([ordered["date"].iloc[0]]),
            dtype=float,
        )
        realised = pd.Series(
            100.0 * (1.0 + ordered[return_column]).cumprod().to_numpy(),
            index=pd.DatetimeIndex(ordered["end_date"]),
            dtype=float,
        )
        path = pd.concat([initial, realised])
        path = path[~path.index.duplicated(keep="last")].sort_index()
        paths[int(offset)] = path
    return paths


def load_benchmark() -> pd.Series:
    require_file(BENCHMARK_PATH, "mettre à jour les données Bloomberg")
    frame = pd.read_csv(BENCHMARK_PATH, parse_dates=["date"]).sort_values("date")
    if "px_last" not in frame.columns:
        raise ValueError("La colonne px_last est absente du benchmark WLS.")
    values = pd.to_numeric(frame["px_last"], errors="coerce")
    result = pd.Series(values.to_numpy(), index=pd.DatetimeIndex(frame["date"]), dtype=float)
    return result.dropna()


def aligned_strategy_curves() -> pd.DataFrame:
    """Aligne les deux stratégies et le WLS sur les vendredis de leur fenêtre commune."""

    five_week = load_periods(FIVE_WEEK_PATH, 5)
    one_week = load_periods(ONE_WEEK_PATH, 1)
    five_paths = nav_paths(five_week, 5)
    weekly_path = nav_paths(one_week, 1)[0]

    all_paths = [*five_paths.values(), weekly_path]
    start = max(path.index.min() for path in all_paths)
    end = min(path.index.max() for path in all_paths)
    grid = pd.date_range(start=start, end=end, freq="W-FRI")

    aligned_five = {}
    for offset, path in five_paths.items():
        expanded = path.reindex(path.index.union(grid)).sort_index().ffill().reindex(grid)
        aligned_five[f"offset_{offset}"] = expanded
    five_frame = pd.DataFrame(aligned_five).dropna()
    grid = five_frame.index.intersection(grid)

    weekly = (
        weekly_path.reindex(weekly_path.index.union(grid))
        .sort_index()
        .ffill()
        .reindex(grid)
    )
    benchmark = load_benchmark()
    benchmark = (
        benchmark.reindex(benchmark.index.union(grid)).sort_index().ffill().reindex(grid)
    )

    valid = five_frame.index.intersection(weekly.dropna().index).intersection(
        benchmark.dropna().index
    )
    five_frame = five_frame.reindex(valid)
    weekly = weekly.reindex(valid)
    benchmark = benchmark.reindex(valid)

    five_rebased = 100.0 * five_frame / five_frame.iloc[0]
    weekly_rebased = 100.0 * weekly / weekly.iloc[0]
    benchmark_rebased = 100.0 * benchmark / benchmark.iloc[0]

    result = five_rebased.copy()
    result["5 semaines sans stop"] = five_rebased.mean(axis=1)
    result["1 semaine continue"] = weekly_rebased
    result["WLS"] = benchmark_rebased
    return result


def relative_to_wls(curves: pd.DataFrame) -> pd.DataFrame:
    result = pd.DataFrame(index=curves.index)
    for column in ("5 semaines sans stop", "1 semaine continue"):
        result[column] = 100.0 * curves[column] / curves["WLS"]
    return result
