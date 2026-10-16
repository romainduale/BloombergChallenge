from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

PROFILE_PATH = Path("config/final_strategy_profiles.json")
DEFAULT_STRATEGY_PROFILE = "agressif"


@dataclass(frozen=True)
class StrategyProfile:
    name: str
    tail_weight: float
    elastic_weight: float
    kappa: float
    max_correlation: float
    max_position_weight: float
    top_n: int
    shortlist_size: int

    def __post_init__(self) -> None:
        if not np.isclose(self.tail_weight + self.elastic_weight, 1.0):
            raise ValueError("Les poids Tail et Elastic doivent totaliser 100 %.")
        if min(self.tail_weight, self.elastic_weight) < 0:
            raise ValueError("Les poids des modèles ne peuvent pas être négatifs.")
        if self.kappa < 0:
            raise ValueError("Kappa ne peut pas être négatif.")
        if not 0 <= self.max_correlation <= 1:
            raise ValueError("La corrélation maximale doit être comprise entre 0 et 1.")
        if not 0 < self.max_position_weight <= 0.20:
            raise ValueError("Le poids maximal doit être compris entre 0 et 20 %.")
        if self.top_n < self.shortlist_size:
            raise ValueError("top_n doit être supérieur ou égal à shortlist_size.")
        if self.shortlist_size * self.max_position_weight < 1.0 - 1e-12:
            raise ValueError("La shortlist et le poids maximal ne permettent pas d'investir 100 %.")


def load_strategy_profiles(path: Path = PROFILE_PATH) -> dict[str, StrategyProfile]:
    raw_profiles = json.loads(path.read_text(encoding="utf-8"))
    return {
        name: StrategyProfile(name=name, **parameters) for name, parameters in raw_profiles.items()
    }


def load_strategy_profile(
    name: str = DEFAULT_STRATEGY_PROFILE,
    path: Path = PROFILE_PATH,
) -> StrategyProfile:
    profiles = load_strategy_profiles(path)
    if name not in profiles:
        available = ", ".join(sorted(profiles))
        raise KeyError(f"Profil stratégique inconnu {name!r}. Disponibles : {available}")
    return profiles[name]
