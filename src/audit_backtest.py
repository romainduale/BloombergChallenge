from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

PRICES_PATH = Path("data/bloomberg/data/prices_10y.csv.gz")
VOLUMES_PATH = Path("data/bloomberg/data/volumes_10y.csv.gz")
UNIVERSE_PATH = Path("data/bloomberg/data/universe.csv")
HISTORY_UNIVERSE_PATH = Path("data/bloomberg/data/history_universe.csv")
EPS_HISTORY_PATH = Path("data/eps_history_5y.csv.gz")


def max_drawdown(returns: pd.Series) -> float:
    wealth = (1.0 + returns).cumprod()
    return float((wealth / wealth.cummax() - 1.0).min())


def summarize_group(group: pd.DataFrame) -> dict[str, float | int | str]:
    ordered = group.sort_values("date")
    net_wealth = float((1.0 + ordered["net_return_5w"]).prod())
    gross_wealth = float((1.0 + ordered["gross_return_5w"]).prod())
    benchmark_wealth = float((1.0 + ordered["benchmark_return_5w"]).prod())
    return {
        "n_periods": len(ordered),
        "start_date": str(ordered["date"].min().date()),
        "end_date": str(ordered["end_date"].max().date()),
        "gross_return": gross_wealth - 1.0,
        "net_return": net_wealth - 1.0,
        "benchmark_return": benchmark_wealth - 1.0,
        "gross_relative_return": gross_wealth / benchmark_wealth - 1.0,
        "net_relative_return": net_wealth / benchmark_wealth - 1.0,
        "mean_net_excess_5w": float(ordered["net_excess_5w"].mean()),
        "median_net_excess_5w": float(ordered["net_excess_5w"].median()),
        "win_rate": float(ordered["net_excess_5w"].gt(0).mean()),
        "net_excess_volatility_5w": float(ordered["net_excess_5w"].std()),
        "max_drawdown": max_drawdown(ordered["net_return_5w"]),
        "average_one_way_turnover": float(ordered["one_way_turnover"].mean()),
        "total_cost_return": float(ordered["total_cost_return"].sum()),
        "average_cost_return": float(ordered["total_cost_return"].mean()),
        "stop_rate_per_period": float(ordered["n_stops"].mean()),
        "limit_fill_rate": float(ordered["limit_fills"].sum() / ordered["limit_candidates"].sum())
        if ordered["limit_candidates"].sum() > 0
        else np.nan,
        "maximum_observed_weight": float(ordered["max_weight"].max()),
    }


def yearly_tables(periods: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = periods.copy()
    data["year"] = data["date"].dt.year
    rows = []
    for (offset, year), group in data.groupby(["offset", "year"]):
        rows.append({"offset": int(offset), "year": int(year), **summarize_group(group)})
    by_offset = pd.DataFrame(rows)

    metric_columns = [
        column
        for column in by_offset.columns
        if column not in {"offset", "year", "start_date", "end_date", "n_periods"}
    ]
    summary = by_offset.groupby("year")[metric_columns].agg(["mean", "min", "max"])
    summary.columns = [f"{metric}_{stat}" for metric, stat in summary.columns]
    summary = summary.reset_index()
    period_counts = by_offset.groupby("year")["n_periods"].sum().rename("n_periods_total")
    summary = summary.merge(period_counts, on="year", how="left")
    return by_offset, summary


def build_bias_table() -> pd.DataFrame:
    prices = pd.read_csv(PRICES_PATH)
    volumes = pd.read_csv(VOLUMES_PATH)
    universe = pd.read_csv(UNIVERSE_PATH)
    history_universe = pd.read_csv(HISTORY_UNIVERSE_PATH)
    eps = pd.read_csv(EPS_HISTORY_PATH)

    if "index_weight" in history_universe.columns:
        history_weight = float(history_universe["index_weight"].sum())
    elif "index_weight_pct" in history_universe.columns:
        history_weight = float(history_universe["index_weight_pct"].sum()) / 100.0
    else:
        history_weight = np.nan
    return pd.DataFrame(
        [
            {
                "bias": "survivorship",
                "status": "material",
                "evidence": (
                    f"Historique limité à {prices.shape[1] - 1:,} titres contre "
                    f"{len(universe):,} dans l'univers snapshot; poids couvert "
                    f"{history_weight:.2%}."
                ),
                "mitigation": "Extraire les compositions WLS historiques point-in-time.",
            },
            {
                "bias": "missing_data",
                "status": "material",
                "evidence": (
                    f"Couverture prix {prices.iloc[:, 1:].notna().mean().mean():.2%}; "
                    f"volumes {volumes.iloc[:, 1:].notna().mean().mean():.2%}; "
                    f"EPS mensuel {eps.iloc[:, 1:].notna().mean().mean():.2%}."
                ),
                "mitigation": (
                    "Publier les taux de couverture par date et éviter l'imputation cachée."
                ),
            },
            {
                "bias": "currencies",
                "status": "unresolved",
                "evidence": (
                    "Aucun historique FX ni champ devise exploitable dans les séries de prix."
                ),
                "mitigation": "Convertir les rendements en USD avant comparaison au WLS.",
            },
            {
                "bias": "adjusted_prices",
                "status": "unresolved",
                "evidence": (
                    "La politique homogène d'ajustement dividendes/splits n'est pas documentée."
                ),
                "mitigation": "Figer un champ Bloomberg total-return ou adjusted-price vérifié.",
            },
            {
                "bias": "eps_timing",
                "status": "partially_mitigated",
                "evidence": (
                    "Les EPS sont regroupés par mois; les dates exactes de disponibilité "
                    "par titre ne sont pas conservées."
                ),
                "mitigation": (
                    "La V2 applique un mois de retard; conserver ensuite les dates source exactes."
                ),
            },
        ]
    )


def render_report(
    overall: pd.DataFrame,
    yearly_summary: pd.DataFrame,
    focus: pd.DataFrame,
    extremes: pd.DataFrame,
    biases: pd.DataFrame,
) -> str:
    def markdown_table(frame: pd.DataFrame) -> str:
        def display(value: object) -> str:
            if pd.isna(value):
                return ""
            if isinstance(value, (float, np.floating)):
                return f"{float(value):.6g}"
            if isinstance(value, pd.Timestamp):
                return str(value.date())
            return str(value).replace("|", "\\|")

        header = "| " + " | ".join(map(str, frame.columns)) + " |"
        separator = "| " + " | ".join(["---"] * len(frame.columns)) + " |"
        rows = [
            "| " + " | ".join(display(value) for value in row) + " |"
            for row in frame.itertuples(index=False, name=None)
        ]
        return "\n".join([header, separator, *rows])

    return "\n".join(
        [
            "# Audit du backtest avec exécution",
            "",
            "Les rendements séquentiels sont calculés séparément pour chaque offset. "
            "Les lignes agrégées entre offsets servent à mesurer la stabilité, pas à "
            "construire une courbe de richesse unique car leurs périodes se chevauchent.",
            "",
            "## Résumé par offset",
            "",
            markdown_table(overall),
            "",
            "## Résultats annuels moyens et dispersion entre offsets",
            "",
            markdown_table(yearly_summary),
            "",
            "## Focus 2025-2026",
            "",
            markdown_table(focus),
            "",
            "## Meilleures et pires périodes",
            "",
            markdown_table(extremes),
            "",
            "## Biais et limites",
            "",
            markdown_table(biases),
            "",
        ]
    )


def audit(periods: pd.DataFrame, output_dir: Path) -> None:
    data = periods.copy()
    data["date"] = pd.to_datetime(data["date"])
    data["end_date"] = pd.to_datetime(data["end_date"])

    overall = pd.DataFrame(
        [
            {"offset": int(offset), **summarize_group(group)}
            for offset, group in data.groupby("offset")
        ]
    )
    yearly_by_offset, yearly_summary = yearly_tables(data)
    focus = yearly_by_offset[yearly_by_offset["year"].isin([2025, 2026])].copy()

    ranked = data.sort_values("net_excess_5w")
    extremes = pd.concat(
        [
            ranked.head(5).assign(extreme="worst"),
            ranked.tail(5).sort_values("net_excess_5w", ascending=False).assign(extreme="best"),
        ],
        ignore_index=True,
    )[
        [
            "extreme",
            "offset",
            "date",
            "end_date",
            "net_excess_5w",
            "net_return_5w",
            "benchmark_return_5w",
            "one_way_turnover",
            "total_cost_return",
            "n_stops",
        ]
    ]
    biases = build_bias_table()

    output_dir.mkdir(parents=True, exist_ok=True)
    overall.to_csv(output_dir / "overall_by_offset.csv", index=False)
    yearly_by_offset.to_csv(output_dir / "yearly_by_offset.csv", index=False)
    yearly_summary.to_csv(output_dir / "yearly_summary.csv", index=False)
    focus.to_csv(output_dir / "focus_2025_2026.csv", index=False)
    extremes.to_csv(output_dir / "best_worst_periods.csv", index=False)
    biases.to_csv(output_dir / "biases.csv", index=False)
    report = render_report(overall, yearly_summary, focus, extremes, biases)
    (output_dir / "audit_report.md").write_text(report, encoding="utf-8")

    machine_summary = {
        "n_periods": int(len(data)),
        "offsets": sorted(data["offset"].unique().astype(int).tolist()),
        "date_min": str(data["date"].min().date()),
        "date_max": str(data["end_date"].max().date()),
        "mean_net_excess_5w": float(data["net_excess_5w"].mean()),
        "win_rate": float(data["net_excess_5w"].gt(0).mean()),
        "mean_one_way_turnover": float(data["one_way_turnover"].mean()),
        "mean_transaction_cost_return": float(data["total_cost_return"].mean()),
        "maximum_observed_weight": float(data["max_weight"].max()),
        "positive_offset_ratio": float(overall["net_relative_return"].gt(0).mean()),
        "offset_net_relative_return_std": float(overall["net_relative_return"].std()),
    }
    (output_dir / "audit_summary.json").write_text(
        json.dumps(machine_summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Produit l'audit complet d'un backtest.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    periods = pd.read_csv(args.input, parse_dates=["date", "end_date"])
    audit(periods, args.output_dir)
    print(f"Audit créé dans {args.output_dir}")


if __name__ == "__main__":
    main()
