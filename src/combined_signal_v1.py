from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.elastic_net_transversal import (
    ElasticNetConfig,
    fit_latest_ranking,
    load_panel,
)
from src.tail_model_v1 import (
    fit_latest_tail_ranking,
)

OUTPUT_DIR = Path("data/processed/combined_signal")

TAIL_WEIGHT = 0.75
ELASTIC_WEIGHT = 0.25


def build_combined_signal() -> pd.DataFrame:
    """
    Combine les deux signaux :

    - Tail Model :
      probabilité d'être dans le top 10 % futur.

    - Elastic Net :
      score de surperformance relative attendue.

    On combine leurs RANGS,
    pas leurs valeurs brutes,
    car ils ne sont pas sur la même échelle.
    """

    config = ElasticNetConfig()

    print("Chargement du panel...")

    df = load_panel()

    print("Calcul du classement Elastic Net...")

    elastic = fit_latest_ranking(
        df,
        config=config,
    )

    print("Calcul du classement Tail...")

    tail = fit_latest_tail_ranking(
        df,
        config=config,
    )

    # On garde les colonnes utiles
    elastic = elastic[
        [
            "date",
            "id",
            "predicted_excess_return",
            "predicted_rank",
        ]
    ].rename(columns={"predicted_rank": ("elastic_rank")})

    tail = tail[
        [
            "date",
            "id",
            "tail_probability",
            "tail_rank",
        ]
    ]

    # On fusionne les deux modèles
    combined = elastic.merge(
        tail,
        on=[
            "date",
            "id",
        ],
        how="inner",
    )

    # Score final
    combined["combined_score"] = (
        TAIL_WEIGHT * combined["tail_rank"] + ELASTIC_WEIGHT * combined["elastic_rank"]
    )

    # Rang final
    combined["combined_rank"] = combined["combined_score"].rank(
        pct=True,
        method="average",
    )

    combined = combined.sort_values(
        "combined_score",
        ascending=False,
    ).reset_index(drop=True)

    return combined


def main():
    combined = build_combined_signal()

    print("\n")
    print("=" * 70)
    print("TOP 30 - SCORE COMBINÉ")
    print("=" * 70)

    columns_to_print = [
        "date",
        "id",
        "tail_probability",
        "tail_rank",
        "predicted_excess_return",
        "elastic_rank",
        "combined_score",
        "combined_rank",
    ]

    print(combined[columns_to_print].head(30).to_string(index=False))

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = OUTPUT_DIR / "latest_combined_signal_v1.csv"

    combined.to_csv(
        output_path,
        index=False,
    )

    print("\n")
    print(f"Fichier créé : {output_path}")


if __name__ == "__main__":
    main()
