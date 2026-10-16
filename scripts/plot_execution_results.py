from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
from plot_strategy_helpers import COMPARISON_PATH, require_file

require_file(COMPARISON_PATH, ".venv/bin/python -m src.run_weekly_research")
comparison = pd.read_csv(COMPARISON_PATH).sort_values("horizon_weeks")
labels = comparison["horizon_weeks"].map(
    {1: "1 semaine\nrebalancée", 5: "5 semaines\nsans stop"}
)
colors = ["#ED7D31", "#1F4E78"]


def plot_metric(column: str, title: str, ylabel: str, *, percentage: bool = True) -> None:
    values = comparison[column].astype(float)
    displayed = 100.0 * values if percentage else values
    figure, axis = plt.subplots(figsize=(8, 5))
    bars = axis.bar(labels, displayed, color=colors)
    axis.axhline(0, color="#555555", linewidth=1)
    axis.set_title(title)
    axis.set_ylabel(ylabel)
    axis.grid(axis="y", alpha=0.25)
    axis.bar_label(
        bars,
        labels=[f"{value:.2f}%" if percentage else f"{value:.2f}" for value in displayed],
        padding=4,
    )
    figure.tight_layout()
    plt.show()


plot_metric(
    "equivalent_relative_return_5w",
    "Surperformance nette équivalente sur 5 semaines",
    "Surperformance relative (%)",
)
plot_metric("win_rate", "Taux de victoire", "Périodes positives (%)")
plot_metric(
    "annualized_one_way_turnover",
    "Turnover one-way annualisé",
    "Turnover annualisé (%)",
)
plot_metric(
    "annualized_cost_linear",
    "Coûts de transaction annualisés indicatifs",
    "Coûts annualisés (%)",
)
plot_metric(
    "worst_max_drawdown_by_path",
    "Pire drawdown historique",
    "Drawdown (%)",
)
plot_metric(
    "information_ratio",
    "Information ratio annualisé",
    "Information ratio",
    percentage=False,
)
