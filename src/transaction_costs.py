from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.trading_config import ExecutionConfig


@dataclass(frozen=True)
class TurnoverResult:
    one_way_turnover: float
    traded_notional: float
    transaction_cost_return: float


def _clean_weights(weights: pd.Series | dict[str, float]) -> pd.Series:
    series = pd.Series(weights, dtype=float)
    if series.empty:
        return series
    if not np.isfinite(series.to_numpy()).all():
        raise ValueError("Les poids doivent être finis.")
    if (series < -1e-12).any():
        raise ValueError("Les poids négatifs ne sont pas autorisés.")
    return series.clip(lower=0.0)


def calculate_turnover(
    previous_weights: pd.Series | dict[str, float],
    target_weights: pd.Series | dict[str, float],
    config: ExecutionConfig,
    *,
    previous_cash_weight: float | None = None,
    target_cash_weight: float | None = None,
) -> TurnoverResult:
    """
    Calcule le turnover et le coût d'un rebalancement.

    Le turnover « one-way » vaut la moitié de la variation absolue des poids,
    cash compris. Le notionnel réellement échangé est la somme des variations
    absolues des poids des actifs. Le coût en rendement applique commissions et
    slippage à ce notionnel.
    """

    previous = _clean_weights(previous_weights)
    target = _clean_weights(target_weights)
    assets = previous.index.union(target.index)
    previous = previous.reindex(assets, fill_value=0.0)
    target = target.reindex(assets, fill_value=0.0)

    previous_cash = (
        max(0.0, 1.0 - float(previous.sum()))
        if previous_cash_weight is None
        else float(previous_cash_weight)
    )
    target_cash = (
        max(0.0, 1.0 - float(target.sum()))
        if target_cash_weight is None
        else float(target_cash_weight)
    )

    if previous_cash < -1e-12 or target_cash < -1e-12:
        raise ValueError("Le poids cash ne peut pas être négatif.")

    asset_changes = (target - previous).abs()
    traded_notional = float(asset_changes.sum())
    one_way_turnover = 0.5 * (traded_notional + abs(target_cash - previous_cash))
    transaction_cost_return = traded_notional * config.total_cost_bps / 10_000.0

    return TurnoverResult(
        one_way_turnover=one_way_turnover,
        traded_notional=traded_notional,
        transaction_cost_return=transaction_cost_return,
    )


def drift_weights(
    weights: pd.Series,
    asset_returns: pd.Series,
    *,
    cash_weight: float = 0.0,
) -> tuple[pd.Series, float]:
    """Transforme les poids de départ en poids pré-rebalancement après performance."""

    weights = _clean_weights(weights)
    returns = pd.Series(asset_returns, dtype=float).reindex(weights.index)
    if returns.isna().any():
        missing = returns.index[returns.isna()].tolist()
        raise ValueError(f"Rendements manquants pour : {missing}")

    ending_assets = weights * (1.0 + returns)
    ending_cash = float(cash_weight)
    ending_value = float(ending_assets.sum() + ending_cash)
    if ending_value <= 0:
        raise ValueError("La valeur finale du portefeuille doit rester positive.")

    return ending_assets / ending_value, ending_cash / ending_value
