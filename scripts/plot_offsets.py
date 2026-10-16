from __future__ import annotations

import matplotlib.pyplot as plt
from plot_strategy_helpers import aligned_strategy_curves

curves = aligned_strategy_curves()
offset_columns = [column for column in curves.columns if column.startswith("offset_")]

figure, axis = plt.subplots(figsize=(14, 7))
for column in offset_columns:
    axis.plot(
        curves.index,
        curves[column],
        color="#9DC3E6",
        linewidth=1,
        alpha=0.75,
        label="Offsets 5 semaines" if column == offset_columns[0] else None,
    )

axis.fill_between(
    curves.index,
    curves[offset_columns].min(axis=1),
    curves[offset_columns].max(axis=1),
    color="#D9EAF7",
    alpha=0.35,
    label="Dispersion des offsets",
)
axis.plot(
    curves.index,
    curves["5 semaines sans stop"],
    color="#1F4E78",
    linewidth=3,
    label="5 semaines sans stop, moyenne",
)
axis.plot(
    curves.index,
    curves["1 semaine continue"],
    color="#ED7D31",
    linewidth=2.5,
    label="1 semaine, rebalancement continu",
)
axis.plot(
    curves.index,
    curves["WLS"],
    color="#333333",
    linewidth=2,
    linestyle="--",
    label="WLS",
)
axis.set_title("Stratégie 1 semaine comparée aux offsets de la stratégie 5 semaines")
axis.set_xlabel("Date")
axis.set_ylabel("Valeur du portefeuille, base 100")
axis.grid(alpha=0.25)
axis.legend()
figure.tight_layout()
plt.show()
