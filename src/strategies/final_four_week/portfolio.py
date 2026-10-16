from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from src.covariance import estimate_ledoit_wolf
from src.risk_screen_v1 import MIN_OBSERVATIONS, build_excess_returns, covariance_to_correlation
from src.robust_optimizer_v1 import portfolio_risk
from src.strategies.final_four_week.config import (
    DEFAULT_STRATEGY_PROFILE,
    StrategyProfile,
    load_strategy_profile,
)
from src.strategies.final_four_week.constants import (
    CORE_PORTFOLIO_PATH,
    HORIZON_WEEKS,
    OUTPUT_ROOT,
    SIGNAL_PATH,
)

COVARIANCE_PATH = OUTPUT_ROOT / "ledoit_wolf_excess_covariance_weekly.csv"
CORRELATION_PATH = OUTPUT_ROOT / "ledoit_wolf_excess_correlation.csv"
SHORTLIST_PATH = OUTPUT_ROOT / "shortlist_4w.csv"


def build_shortlist_4w(
    ranking: pd.DataFrame,
    correlation: pd.DataFrame,
    profile: StrategyProfile,
) -> pd.DataFrame:
    eligible = ranking[ranking["id"].isin(correlation.columns)]
    selected: list[str] = []
    selected_rows: list[pd.Series] = []
    for _, row in eligible.iterrows():
        asset = str(row["id"])
        max_correlation = (
            0.0 if not selected else float(correlation.loc[asset, selected].abs().max())
        )
        if max_correlation <= profile.max_correlation:
            accepted = row.copy()
            accepted["max_abs_correlation"] = max_correlation
            selected.append(asset)
            selected_rows.append(accepted)
        if len(selected) >= profile.shortlist_size:
            break
    return pd.DataFrame(selected_rows).reset_index(drop=True)


def optimise_four_week_portfolio(
    shortlist: pd.DataFrame,
    covariance_weekly: pd.DataFrame,
    profile: StrategyProfile,
) -> np.ndarray:
    assets = shortlist["id"].tolist()
    if len(assets) < 1:
        raise ValueError("La shortlist quatre semaines est vide.")
    alpha = shortlist["elastic_net_score"].to_numpy(dtype=float)
    covariance_horizon = covariance_weekly.loc[assets, assets].to_numpy(dtype=float) * HORIZON_WEEKS
    initial_weights = np.repeat(1.0 / len(assets), len(assets))

    def objective(weights: np.ndarray) -> float:
        expected_alpha = float(alpha @ weights)
        risk = portfolio_risk(weights, covariance_horizon)
        return -(expected_alpha - profile.kappa * risk)

    result = minimize(
        objective,
        initial_weights,
        method="SLSQP",
        bounds=[(0.0, profile.max_position_weight) for _ in assets],
        constraints=[{"type": "eq", "fun": lambda weights: np.sum(weights) - 1.0}],
        options={"maxiter": 5000, "ftol": 1e-12},
    )
    if not result.success:
        raise RuntimeError(f"Échec optimisation quatre semaines : {result.message}")
    return result.x


def build_core_portfolio_4w(
    ranking: pd.DataFrame,
    strategy_profile: StrategyProfile | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    profile = strategy_profile or load_strategy_profile(DEFAULT_STRATEGY_PROFILE)
    candidates = ranking.sort_values("combined_score", ascending=False).head(profile.top_n)
    excess_returns = build_excess_returns(candidates)
    covariance_result = estimate_ledoit_wolf(
        excess_returns,
        min_observations=MIN_OBSERVATIONS,
    )
    covariance = covariance_result.covariance_weekly
    correlation = covariance_to_correlation(covariance)
    shortlist = build_shortlist_4w(candidates, correlation, profile)
    minimum_assets = int(np.ceil(1.0 / profile.max_position_weight))
    if len(shortlist) < max(6, minimum_assets):
        raise RuntimeError(
            f"Shortlist insuffisante : {len(shortlist)} titres; "
            f"minimum opérationnel {max(6, minimum_assets)}."
        )

    portfolio = shortlist.copy()
    portfolio["weight"] = optimise_four_week_portfolio(shortlist, covariance, profile)
    portfolio["weight_pct"] = 100.0 * portfolio["weight"]
    portfolio["sleeve"] = "core_4w"
    portfolio["horizon_weeks"] = HORIZON_WEEKS
    portfolio["strategy_profile"] = profile.name
    portfolio = portfolio.sort_values("weight", ascending=False).reset_index(drop=True)
    return portfolio, covariance, correlation


def create_core_portfolio(
    signal_path: Path = SIGNAL_PATH,
    output_path: Path = CORE_PORTFOLIO_PATH,
    *,
    strategy_profile: StrategyProfile | None = None,
) -> pd.DataFrame:
    ranking = pd.read_csv(signal_path, parse_dates=["date"])
    portfolio, covariance, correlation = build_core_portfolio_4w(
        ranking, strategy_profile=strategy_profile
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    portfolio.to_csv(output_path, index=False)
    covariance.to_csv(COVARIANCE_PATH)
    correlation.to_csv(CORRELATION_PATH)
    portfolio.to_csv(SHORTLIST_PATH, index=False)
    return portfolio


def main() -> None:
    portfolio = create_core_portfolio()
    columns = [
        "id",
        "elastic_net_score",
        "tail_score",
        "combined_score",
        "weight_pct",
    ]
    print(portfolio[columns].to_string(index=False))
    print(f"\nPortefeuille cœur quatre semaines : {CORE_PORTFOLIO_PATH}")


if __name__ == "__main__":
    main()
