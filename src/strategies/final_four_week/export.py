from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.market_metadata import infer_currency
from src.strategies.final_four_week.constants import (
    CHALLENGE_END_DATE,
    FEATURE_LABELS,
    FINAL_CSV_PATH,
    HORIZON_WEEKS,
)


def _ordered_diagnostic_columns() -> list[str]:
    columns: list[str] = []
    for label in FEATURE_LABELS.values():
        columns.extend(
            [
                f"feature_{label}",
                f"elastic_beta_{label}",
                f"elastic_contribution_{label}",
                f"tail_beta_{label}",
                f"tail_contribution_{label}",
            ]
        )
    return columns


def build_final_explained_export(
    allocation: pd.DataFrame,
    orders: pd.DataFrame,
    signal: pd.DataFrame,
    *,
    capital: float,
) -> pd.DataFrame:
    if capital <= 0:
        raise ValueError("Le capital doit être strictement positif.")
    required = {"id", "sleeve", "weight"}
    missing = required - set(allocation.columns)
    if missing:
        raise ValueError(f"Colonnes manquantes dans l'allocation : {sorted(missing)}")

    selected = allocation[allocation["weight"].astype(float).gt(1e-12)].copy()
    signal_columns = [
        "id",
        "date",
        "elastic_net_score",
        "elastic_net_rank",
        "tail_score",
        "tail_rank",
        "combined_score",
        "combined_rank",
        "selection_explanation",
        *_ordered_diagnostic_columns(),
    ]
    available_signal_columns = [column for column in signal_columns if column in signal]
    selected = selected.drop(
        columns=[column for column in available_signal_columns if column != "id"],
        errors="ignore",
    ).merge(
        signal[available_signal_columns].drop_duplicates("id"),
        on="id",
        how="left",
        validate="one_to_one",
    )

    order_columns = ["id", "last_price", "price_to_usd_rate", "action", "quantity"]
    available_order_columns = [column for column in order_columns if column in orders]
    selected = selected.drop(
        columns=[column for column in available_order_columns if column != "id"],
        errors="ignore",
    ).merge(
        orders[available_order_columns].drop_duplicates("id", keep="last"),
        on="id",
        how="left",
        validate="one_to_one",
    )
    selected["signal_date"] = pd.to_datetime(selected["date"])
    selected["planned_exit_date"] = selected["signal_date"] + pd.Timedelta(weeks=HORIZON_WEEKS)
    selected["challenge_end_date"] = CHALLENGE_END_DATE
    selected["challenge_aligned"] = selected["planned_exit_date"].eq(CHALLENGE_END_DATE)
    selected["horizon_weeks"] = HORIZON_WEEKS
    selected["allocation_pct"] = 100.0 * selected["weight"].astype(float)
    selected["allocation_usd"] = capital * selected["weight"].astype(float)
    selected["currency"] = selected.get("currency", pd.Series(index=selected.index)).astype(
        "string"
    )
    selected["currency"] = selected["currency"].fillna(selected["id"].map(infer_currency))
    selected["last_price_local"] = pd.to_numeric(selected.get("last_price"), errors="coerce")
    selected["last_price_usd"] = selected["last_price_local"] * pd.to_numeric(
        selected.get("price_to_usd_rate"), errors="coerce"
    )
    selected["estimated_excess_return_4w_pct"] = 100.0 * selected["elastic_net_score"]
    selected["estimated_excess_profit_4w_usd"] = (
        selected["allocation_usd"] * selected["elastic_net_score"]
    )
    selected["opportunity_score"] = pd.to_numeric(
        selected.get("opportunity_score"), errors="coerce"
    )
    if "reason" in selected:
        opportunistic = selected["sleeve"].eq("opportunistic") & selected["reason"].notna()
        selected.loc[opportunistic, "selection_explanation"] = (
            selected.loc[opportunistic, "selection_explanation"].fillna("")
            + " | Opportuniste: "
            + selected.loc[opportunistic, "reason"].astype(str)
        )
    selected["data_quality"] = np.where(
        selected["last_price_usd"].notna(), "OK", "FX_OR_PRICE_MISSING"
    )

    base_columns = [
        "signal_date",
        "planned_exit_date",
        "challenge_end_date",
        "challenge_aligned",
        "horizon_weeks",
        "strategy_profile",
        "id",
        "sleeve",
        "currency",
        "allocation_pct",
        "allocation_usd",
        "last_price_local",
        "last_price_usd",
        "action",
        "quantity",
        "elastic_net_score",
        "elastic_net_rank",
        "tail_score",
        "tail_rank",
        "combined_score",
        "combined_rank",
        "opportunity_score",
        "estimated_excess_return_4w_pct",
        "estimated_excess_profit_4w_usd",
        "selection_explanation",
        "data_quality",
    ]
    output_columns = [column for column in base_columns if column in selected]
    output_columns.extend(column for column in _ordered_diagnostic_columns() if column in selected)
    output = selected[output_columns].sort_values(
        ["sleeve", "allocation_pct"], ascending=[True, False]
    )
    return output.reset_index(drop=True)


def write_final_export(data: pd.DataFrame, path: Path = FINAL_CSV_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(path, index=False)
