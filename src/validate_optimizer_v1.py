from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from src.robust_optimizer_v1 import (
    HORIZON_WEEKS,
    MAX_WEIGHT,
    load_inputs,
    portfolio_risk,
)

KAPPAS = [
    0.00,
    0.05,
    0.10,
    0.15,
    0.20,
    0.30,
    0.50,
]


def optimise_with_kappa(
    alpha: np.ndarray,
    covariance_5w: np.ndarray,
    kappa: float,
) -> np.ndarray:
    n_assets = len(alpha)

    def objective(
        weights: np.ndarray,
    ) -> float:
        expected_alpha = float(alpha @ weights)

        risk = portfolio_risk(
            weights,
            covariance_5w,
        )

        return -(expected_alpha - kappa * risk)

    initial_weights = np.repeat(
        1.0 / n_assets,
        n_assets,
    )

    bounds = [(0.0, MAX_WEIGHT) for _ in range(n_assets)]

    constraints = [
        {
            "type": "eq",
            "fun": lambda w: np.sum(w) - 1.0,
        }
    ]

    result = minimize(
        objective,
        initial_weights,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={
            "maxiter": 5000,
            "ftol": 1e-12,
        },
    )

    if not result.success:
        raise RuntimeError(result.message)

    return result.x


def main():
    shortlist, covariance = load_inputs()

    assets = shortlist["id"].tolist()

    alpha = shortlist["predicted_excess_return"].to_numpy()

    covariance_5w = covariance.to_numpy() * HORIZON_WEEKS

    rows = []

    print("\n")
    print("=" * 75)
    print("TEST DE SENSIBILITÉ - ROBUST OPTIMIZER")
    print("=" * 75)

    for kappa in KAPPAS:
        weights = optimise_with_kappa(
            alpha,
            covariance_5w,
            kappa,
        )

        expected_alpha = float(alpha @ weights)

        risk = portfolio_risk(
            weights,
            covariance_5w,
        )

        rows.append(
            {
                "kappa": kappa,
                "expected_alpha_5w": (expected_alpha),
                "risk_5w": risk,
                "max_weight": (weights.max()),
                "n_positions_gt_1pct": int(np.sum(weights >= 0.01)),
            }
        )

        ranking = sorted(
            zip(
                assets,
                weights,
                strict=False,
            ),
            key=lambda x: x[1],
            reverse=True,
        )

        print(f"\nKAPPA = {kappa:.2f}")

        for asset, weight in ranking:
            if weight >= 0.01:
                print(f"{asset:20s} {weight:6.2%}")

        print(f"Somme = {weights.sum():.6f}")

        print(f"Max = {weights.max():.2%}")

        print(f"Alpha 5w = {expected_alpha:.2%}")

        print(f"Risque 5w = {risk:.2%}")

    results = pd.DataFrame(rows)

    print("\n")
    print("=" * 75)
    print("RÉSUMÉ")
    print("=" * 75)

    print(results.to_string(index=False))


if __name__ == "__main__":
    main()
