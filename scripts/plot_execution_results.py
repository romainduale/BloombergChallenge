from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

base = Path("data/processed/execution_backtest/profile_comparison")

print("Fichiers disponibles :")
for p in base.iterdir():
    print(" -", p.name)

csv_files = list(base.glob("*.csv"))

if not csv_files:
    raise FileNotFoundError("Aucun CSV trouvé dans profile_comparison")

csv_path = csv_files[0]

print(f"\nLecture de : {csv_path}")

df = pd.read_csv(csv_path)

labels = {
    "sans_stop": "Sans stop",
    "stop_fixe": "Stop fixe",
    "equilibre": "Stop volatilité"
}

df["label"] = df["profile"].map(labels)

plt.figure(figsize=(8, 5))
plt.bar(df["label"], 100 * df["mean_net_excess_5w"])
plt.axhline(0, linewidth=1)
plt.ylabel("Excès net moyen à 5 semaines (%)")
plt.title("Performance des profils d'exécution")
plt.grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.show()

plt.figure(figsize=(8, 5))
plt.bar(df["label"], 100 * df["win_rate"])
plt.axhline(50, linestyle="--", label="50 %")
plt.ylabel("Taux de victoire (%)")
plt.title("Taux de victoire")
plt.legend()
plt.grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.show()

plt.figure(figsize=(8, 5))
plt.bar(df["label"], 100 * df["mean_one_way_turnover"])
plt.ylabel("Turnover one-way moyen (%)")
plt.title("Turnover par profil")
plt.grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.show()

plt.figure(figsize=(8, 5))
plt.bar(df["label"], 100 * df["worst_max_drawdown_by_offset"])
plt.ylabel("Pire drawdown (%)")
plt.title("Pire drawdown par profil")
plt.grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.show()