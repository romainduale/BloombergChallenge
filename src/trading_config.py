from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExecutionConfig:
    """Paramètres modifiables des coûts et des règles d'exécution."""

    max_position_weight: float = 0.20
    commission_bps: float = 10.0
    slippage_bps: float = 5.0
    minimum_trade_weight: float = 0.005
    limit_discount_pct: float = 0.005
    limit_valid_days: int = 3
    stop_loss_mode: str = "volatility"
    fixed_stop_loss_pct: float = 0.08
    volatility_lookback_days: int = 20
    volatility_multiplier: float = 1.50
    minimum_stop_pct: float = 0.05
    maximum_stop_pct: float = 0.15
    stop_execution_delay_days: int = 1

    def __post_init__(self) -> None:
        percentages = {
            "max_position_weight": self.max_position_weight,
            "minimum_trade_weight": self.minimum_trade_weight,
            "limit_discount_pct": self.limit_discount_pct,
            "fixed_stop_loss_pct": self.fixed_stop_loss_pct,
            "minimum_stop_pct": self.minimum_stop_pct,
            "maximum_stop_pct": self.maximum_stop_pct,
        }
        for name, value in percentages.items():
            if not 0 <= value <= 1:
                raise ValueError(f"{name} doit être compris entre 0 et 1.")

        if self.max_position_weight > 0.20:
            raise ValueError("Le poids maximum réglementaire est de 20 %.")
        if self.commission_bps < 0 or self.slippage_bps < 0:
            raise ValueError("Les coûts en points de base doivent être positifs.")
        if self.limit_valid_days < 1:
            raise ValueError("La validité d'un ordre limite doit être d'au moins un jour.")
        if self.volatility_lookback_days < 2:
            raise ValueError("La fenêtre de volatilité doit contenir au moins deux jours.")
        if self.volatility_multiplier <= 0:
            raise ValueError("Le multiplicateur de volatilité doit être strictement positif.")
        if self.minimum_stop_pct > self.maximum_stop_pct:
            raise ValueError("Le stop minimum ne peut pas dépasser le stop maximum.")
        if self.stop_loss_mode not in {"none", "fixed", "volatility"}:
            raise ValueError("stop_loss_mode doit valoir none, fixed ou volatility.")
        if self.stop_execution_delay_days not in {0, 1}:
            raise ValueError("Le délai d'exécution du stop doit valoir 0 ou 1 jour.")

    @property
    def total_cost_bps(self) -> float:
        return self.commission_bps + self.slippage_bps


def load_execution_profile(
    profile: str = "sans_stop",
    path: str | Path = "config/execution_profiles.json",
) -> ExecutionConfig:
    profiles = json.loads(Path(path).read_text(encoding="utf-8"))
    if profile not in profiles:
        available = ", ".join(sorted(profiles))
        raise KeyError(f"Profil inconnu {profile!r}. Profils disponibles : {available}")
    return ExecutionConfig(**profiles[profile])
