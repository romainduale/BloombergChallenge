from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

SHORTLIST_PATH = Path("data/processed/risk_screen/shortlist_v1.csv")

COVARIANCE_PATH = Path("data/processed/risk_screen/ledoit_wolf_excess_covariance_weekly.csv")

OUTPUT_DIR = Path("data/processed/portfolio")

MAX_WEIGHT = 0.18

# Robustesse :
# plus KAPPA est élevé,
# plus on pénalise le risque.
KAPPA = 0.15

# Notre alpha prévoit environ 5 semaines.
HORIZON_WEEKS = 5

# On considère une position comme
# significative au-dessus de 0.5 %.
DISPLAY_THRESHOLD = 0.005


def load_inputs() -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    shortlist = pd.read_csv(SHORTLIST_PATH)

    covariance = pd.read_csv(
        COVARIANCE_PATH,
        index_col=0,
    )

    assets = shortlist["id"].tolist()

    missing = [asset for asset in assets if asset not in covariance.index]

    if missing:
        raise ValueError("Actions absentes de la covariance : " + ", ".join(missing))

    covariance = covariance.loc[
        assets,
        assets,
    ]

    return shortlist, covariance


def portfolio_risk(
    weights: np.ndarray,
    covariance_5w: np.ndarray,
) -> float:
    variance = float(weights @ covariance_5w @ weights)

    return float(
        np.sqrt(
            max(
                variance,
                0.0,
            )
        )
    )


def robust_objective(
    weights: np.ndarray,
    alpha: np.ndarray,
    covariance_5w: np.ndarray,
) -> float:
    expected_alpha = float(alpha @ weights)

    risk = portfolio_risk(
        weights,
        covariance_5w,
    )

    robust_score = expected_alpha - KAPPA * risk

    # scipy minimise,
    # donc on met un signe moins.
    return -robust_score


def optimise_portfolio(
    shortlist: pd.DataFrame,
    covariance: pd.DataFrame,
) -> np.ndarray:
    assets = shortlist["id"].tolist()

    n_assets = len(assets)

    alpha = shortlist["predicted_excess_return"].to_numpy(dtype=float)

    # Covariance hebdomadaire
    # -> approximation covariance 5 semaines.
    covariance_5w = covariance.to_numpy(dtype=float) * HORIZON_WEEKS

    initial_weights = np.repeat(
        1.0 / n_assets,
        n_assets,
    )

    bounds = [
        (
            0.0,
            MAX_WEIGHT,
        )
        for _ in range(n_assets)
    ]

    constraints = [
        {
            "type": "eq",
            "fun": lambda w: np.sum(w) - 1.0,
        }
    ]

    result = minimize(
        robust_objective,
        initial_weights,
        args=(
            alpha,
            covariance_5w,
        ),
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={
            "maxiter": 5000,
            "ftol": 1e-12,
        },
    )

    if not result.success:
        raise RuntimeError(f"Échec optimisation : {result.message}")

    return result.x


def build_portfolio() -> pd.DataFrame:
    (
        shortlist,
        covariance,
    ) = load_inputs()

    weights = optimise_portfolio(
        shortlist,
        covariance,
    )

    portfolio = shortlist.copy()

    portfolio["weight"] = weights

    portfolio["weight_pct"] = 100.0 * portfolio["weight"]

    portfolio = portfolio.sort_values(
        "weight",
        ascending=False,
    ).reset_index(drop=True)

    return portfolio


def print_diagnostics(
    portfolio: pd.DataFrame,
    covariance: pd.DataFrame,
) -> None:
    indexed = portfolio.set_index("id")

    assets = indexed.index.tolist()

    weights = indexed["weight"].to_numpy()

    alpha = indexed["predicted_excess_return"].to_numpy()

    covariance_weekly = covariance.loc[
        assets,
        assets,
    ].to_numpy()

    covariance_5w = covariance_weekly * HORIZON_WEEKS

    expected_alpha = float(alpha @ weights)

    risk_5w = portfolio_risk(
        weights,
        covariance_5w,
    )

    annual_tracking_error = float(np.sqrt(weights @ (covariance_weekly * 52) @ weights))

    robust_score = expected_alpha - KAPPA * risk_5w

    significant = portfolio[portfolio["weight"] >= DISPLAY_THRESHOLD]

    print("\n")
    print("=" * 72)
    print("PORTEFEUILLE ROBUSTE V1")
    print("=" * 72)

    print(
        significant[
            [
                "id",
                "combined_score",
                "tail_rank",
                "predicted_excess_return",
                "weight_pct",
            ]
        ].to_string(index=False)
    )

    print("\n")
    print("=" * 72)
    print("DIAGNOSTICS")
    print("=" * 72)

    print(f"Nombre de positions > 0.5 % : {len(significant)}")

    print(f"Poids maximum : {portfolio['weight'].max():.2%}")

    print(f"Somme des poids : {portfolio['weight'].sum():.2%}")

    print(f"Alpha relatif prévu à 5 semaines : {expected_alpha:.2%}")

    print(f"Risque relatif estimé à 5 semaines : {risk_5w:.2%}")

    print(f"Tracking error annualisée indicative : {annual_tracking_error:.2%}")

    print(f"Score robuste : {robust_score:.2%}")


def main():
    (
        shortlist,
        covariance,
    ) = load_inputs()

    portfolio = build_portfolio()

    print_diagnostics(
        portfolio,
        covariance,
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = OUTPUT_DIR / "portfolio_robust_v1.csv"

    portfolio.to_csv(
        output_path,
        index=False,
    )

    print(f"\nFichier créé : {output_path}")


if __name__ == "__main__":
    main()
