from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from src.opportunistic_model import load_config as load_allocation_config
from src.strategies.final_four_week.backtest import run_four_week_backtest
from src.strategies.final_four_week.config import (
    StrategyProfile,
    load_strategy_profile,
    load_strategy_profiles,
)
from src.strategies.final_four_week.constants import HORIZON_WEEKS, PANEL_PATH
from src.strategies.final_four_week.features import create_panel
from src.strategies.final_four_week.models import fit_latest_four_week_models
from src.strategies.final_four_week.portfolio import build_core_portfolio_4w

DEFAULT_OUTPUT_DIR = Path("data/processed/strategies/profile_comparison")


def ranking_for_profile(
    base_ranking: pd.DataFrame,
    profile: StrategyProfile,
) -> pd.DataFrame:
    ranking = base_ranking.copy()
    ranking["combined_score"] = (
        profile.tail_weight * ranking["tail_rank"]
        + profile.elastic_weight * ranking["elastic_net_rank"]
    )
    ranking["combined_rank"] = ranking["combined_score"].rank(pct=True, method="average")
    ranking["strategy_profile"] = profile.name
    return ranking.sort_values("combined_score", ascending=False).reset_index(drop=True)


def forecast_summary(
    portfolio: pd.DataFrame,
    profile: StrategyProfile,
    *,
    capital: float,
    core_weight: float,
) -> dict[str, float | int | str]:
    weights = portfolio["weight"].astype(float)
    predicted_excess_return = float(weights @ portfolio["elastic_net_score"].astype(float))
    weighted_tail_score = float(weights @ portfolio["tail_score"].astype(float))
    profile_parameters = asdict(profile)
    profile_parameters.pop("name")
    return {
        "strategy_profile": profile.name,
        **profile_parameters,
        "forecast_signal_date": str(pd.Timestamp(portfolio["date"].max()).date()),
        "forecast_core_positions": int(weights.gt(0.005).sum()),
        "forecast_max_weight_core": float(weights.max()),
        "forecast_max_weight_total": float(core_weight * weights.max()),
        "forecast_concentration_hhi": float(weights.pow(2).sum()),
        "forecast_core_excess_return_4w": predicted_excess_return,
        "forecast_core_excess_profit_4w_usd": (capital * core_weight * predicted_excess_return),
        "forecast_weighted_tail_score": weighted_tail_score,
    }


def _max_drawdown(returns: pd.Series) -> float:
    wealth = (1.0 + returns.astype(float)).cumprod()
    return float((wealth / wealth.cummax() - 1.0).min())


def backtest_summary(periods: pd.DataFrame) -> dict[str, float | int]:
    metric = f"net_excess_{HORIZON_WEEKS}w"
    gross_metric = f"gross_excess_{HORIZON_WEEKS}w"
    excess = periods[metric].astype(float)
    drawdowns = [
        _max_drawdown(group.sort_values("date")[metric]) for _, group in periods.groupby("offset")
    ]
    information_ratio = (
        np.nan
        if excess.std() == 0 or pd.isna(excess.std())
        else float(excess.mean() / excess.std() * np.sqrt(52.0 / HORIZON_WEEKS))
    )
    return {
        "backtest_periods": int(len(periods)),
        "backtest_paths": int(periods["offset"].nunique()),
        "backtest_mean_gross_excess_4w": float(periods[gross_metric].mean()),
        "backtest_mean_net_excess_4w": float(excess.mean()),
        "backtest_median_net_excess_4w": float(excess.median()),
        "backtest_win_rate": float(excess.gt(0).mean()),
        "backtest_excess_volatility_4w": float(excess.std()),
        "backtest_information_ratio": information_ratio,
        "backtest_worst_period": float(excess.min()),
        "backtest_best_period": float(excess.max()),
        "backtest_mean_one_way_turnover": float(periods["one_way_turnover"].mean()),
        "backtest_mean_cost": float(periods["total_cost_return"].mean()),
        "backtest_mean_max_drawdown": float(np.mean(drawdowns)),
        "backtest_worst_max_drawdown": float(np.min(drawdowns)),
        "backtest_mean_positions": float(periods["n_positions"].mean()),
        "backtest_mean_max_weight": float(periods["max_weight"].mean()),
    }


def common_periods_by_profile(
    results: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    common_keys: set[tuple[int, pd.Timestamp, pd.Timestamp]] | None = None
    normalized: dict[str, pd.DataFrame] = {}
    for name, frame in results.items():
        data = frame.copy()
        data["date"] = pd.to_datetime(data["date"])
        data["end_date"] = pd.to_datetime(data["end_date"])
        normalized[name] = data
        keys = set(data[["offset", "date", "end_date"]].itertuples(index=False, name=None))
        common_keys = keys if common_keys is None else common_keys.intersection(keys)
    if not common_keys:
        raise RuntimeError("Aucune période commune aux profils stratégiques.")
    return {
        name: frame[
            frame[["offset", "date", "end_date"]].apply(tuple, axis=1).isin(common_keys)
        ].copy()
        for name, frame in normalized.items()
    }


def render_markdown(summary: pd.DataFrame) -> str:
    columns = [
        "strategy_profile",
        "forecast_core_excess_return_4w",
        "forecast_core_excess_profit_4w_usd",
        "backtest_mean_net_excess_4w",
        "backtest_win_rate",
        "backtest_worst_period",
        "backtest_worst_max_drawdown",
        "backtest_information_ratio",
        "backtest_mean_one_way_turnover",
        "backtest_mean_cost",
    ]
    labels = {
        "strategy_profile": "Profil",
        "forecast_core_excess_return_4w": "Prévision cœur 4s",
        "forecast_core_excess_profit_4w_usd": "Profit relatif prévu cœur",
        "backtest_mean_net_excess_4w": "Excès net moyen 4s",
        "backtest_win_rate": "Taux de victoire",
        "backtest_worst_period": "Pire période",
        "backtest_worst_max_drawdown": "Pire drawdown",
        "backtest_information_ratio": "Information ratio",
        "backtest_mean_one_way_turnover": "Turnover moyen",
        "backtest_mean_cost": "Coût moyen",
    }
    displayed = summary[columns].rename(columns=labels).copy()
    percentage_columns = [
        "Prévision cœur 4s",
        "Excès net moyen 4s",
        "Taux de victoire",
        "Pire période",
        "Pire drawdown",
        "Turnover moyen",
        "Coût moyen",
    ]
    for column in percentage_columns:
        displayed[column] = displayed[column].map(lambda value: f"{value:.2%}")
    displayed["Profit relatif prévu cœur"] = displayed["Profit relatif prévu cœur"].map(
        lambda value: f"${value:,.0f}"
    )
    displayed["Information ratio"] = displayed["Information ratio"].map(
        lambda value: f"{value:.2f}"
    )
    header = "| " + " | ".join(displayed.columns) + " |"
    separator = "| " + " | ".join(["---"] * len(displayed.columns)) + " |"
    rows = [
        "| " + " | ".join(map(str, row)) + " |"
        for row in displayed.itertuples(index=False, name=None)
    ]
    return "\n".join(
        [
            "# Comparaison des profils stratégiques quatre semaines",
            "",
            "La prévision de profit concerne uniquement le cœur de 80 % et représente "
            "une surperformance estimée face au WLS, pas un profit garanti. Les métriques "
            "historiques utilisent exactement les mêmes périodes communes.",
            "",
            header,
            separator,
            *rows,
            "",
        ]
    )


def parse_args() -> argparse.Namespace:
    available = sorted(load_strategy_profiles())
    parser = argparse.ArgumentParser(
        description="Compare les profils prudent, intermédiaire et agressif."
    )
    parser.add_argument("--profiles", nargs="+", choices=available, default=available)
    parser.add_argument("--execution-profile", default="sans_stop")
    parser.add_argument("--capital", type=float, default=1_000_000.0)
    parser.add_argument("--panel", type=Path, default=PANEL_PATH)
    parser.add_argument("--rebuild-features", action="store_true")
    parser.add_argument("--forecast-only", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.rebuild_features or not args.panel.exists():
        panel = create_panel(args.panel)
    else:
        panel = pd.read_csv(args.panel, parse_dates=["date"])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    allocation_dir = args.output_dir / "latest_core_allocations"
    allocation_dir.mkdir(parents=True, exist_ok=True)

    profiles = [load_strategy_profile(name) for name in args.profiles]
    base_model_result = fit_latest_four_week_models(
        panel,
        strategy_profile=profiles[0],
    )
    allocation_config = load_allocation_config()
    forecasts: dict[str, dict[str, float | int | str]] = {}
    raw_backtests: dict[str, pd.DataFrame] = {}

    for profile in profiles:
        print(f"\nPROFIL {profile.name.upper()} — prévision actuelle")
        ranking = ranking_for_profile(base_model_result.ranking, profile)
        portfolio, _, _ = build_core_portfolio_4w(
            ranking,
            strategy_profile=profile,
        )
        portfolio.to_csv(allocation_dir / f"{profile.name}.csv", index=False)
        forecasts[profile.name] = forecast_summary(
            portfolio,
            profile,
            capital=args.capital,
            core_weight=allocation_config.core_weight,
        )
        if not args.forecast_only:
            print(f"PROFIL {profile.name.upper()} — backtest walk-forward")
            periods, holdings = run_four_week_backtest(
                panel,
                execution_profile=args.execution_profile,
                strategy_profile=profile,
            )
            raw_backtests[profile.name] = periods
            profile_dir = args.output_dir / profile.name
            profile_dir.mkdir(parents=True, exist_ok=True)
            periods.to_csv(profile_dir / "periods.csv", index=False)
            holdings.to_csv(profile_dir / "holdings.csv", index=False)

    if raw_backtests:
        comparable_backtests = common_periods_by_profile(raw_backtests)
    else:
        comparable_backtests = {}

    rows = []
    for profile in profiles:
        row = forecasts[profile.name]
        if profile.name in comparable_backtests:
            row = {**row, **backtest_summary(comparable_backtests[profile.name])}
        rows.append(row)
    summary = pd.DataFrame(rows)
    summary.to_csv(args.output_dir / "profile_comparison.csv", index=False)
    if comparable_backtests:
        (args.output_dir / "profile_comparison.md").write_text(
            render_markdown(summary), encoding="utf-8"
        )
    print("\n" + summary.to_string(index=False))
    print(f"\nRésultats : {args.output_dir}")


if __name__ == "__main__":
    main()
