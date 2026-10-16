from __future__ import annotations

import matplotlib.pyplot as plt
from plot_strategy_helpers import aligned_strategy_curves, relative_to_wls

curves = aligned_strategy_curves()

figure, axis = plt.subplots(figsize=(14, 7))
axis.plot(
    curves.index,
    curves["WLS"],
    color="#333333",
    linewidth=2.5,
    linestyle="--",
    label="WLS",
)
axis.plot(
    curves.index,
    curves["5 semaines sans stop"],
    color="#1F4E78",
    linewidth=3,
    label="5 semaines sans stop",
)
axis.plot(
    curves.index,
    curves["1 semaine continue"],
    color="#ED7D31",
    linewidth=2.5,
    label="1 semaine, rebalancement continu",
)
axis.set_title("WLS et stratégies sans stop")
axis.set_xlabel("Date")
axis.set_ylabel("Valeur normalisée, base 100")
axis.grid(alpha=0.25)
axis.legend()
figure.tight_layout()
plt.show()

relative = relative_to_wls(curves)
figure, axis = plt.subplots(figsize=(14, 7))
axis.plot(
    relative.index,
    relative["5 semaines sans stop"],
    color="#1F4E78",
    linewidth=3,
    label="5 semaines sans stop",
)
axis.plot(
    relative.index,
    relative["1 semaine continue"],
    color="#ED7D31",
    linewidth=2.5,
    label="1 semaine, rebalancement continu",
)
axis.axhline(
    100.0,
    color="#333333",
    linewidth=1,
    linestyle="--",
    label="Même performance que le WLS",
)
axis.set_title("Performance relative au WLS")
axis.set_xlabel("Date")
axis.set_ylabel("Richesse relative, base 100")
axis.grid(alpha=0.25)
axis.legend()
figure.tight_layout()
plt.show()
