from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


BASE = Path("data/processed/execution_backtest")

STRATEGIES = {
    "Sans stop": BASE / "v1_sans_stop" / "periods.csv",
    "Stop fixe": BASE / "v1_stop_fixe" / "periods.csv",
    "Stop volatilité": BASE / "v1_equilibre" / "periods.csv",
}


# ============================================================
# WLS
# ============================================================

benchmark = pd.read_csv(
    "data/bloomberg/data/benchmark_10y.csv"
)

print("Benchmark columns:", benchmark.columns.tolist())

date_col = "date" if "date" in benchmark.columns else benchmark.columns[0]

benchmark[date_col] = pd.to_datetime(benchmark[date_col])

numeric = [
    c for c in benchmark.columns
    if c != date_col
    and pd.api.types.is_numeric_dtype(benchmark[c])
]

print("Numeric benchmark columns:", numeric)

# utilise première colonne numérique comme niveau benchmark
level_col = numeric[0]

benchmark = benchmark.sort_values(date_col)

benchmark["NAV"] = (
    100
    * benchmark[level_col]
    / benchmark[level_col].iloc[0]
)


# ============================================================
# GRAPH WLS 10Y
# ============================================================

plt.figure(figsize=(13, 6))

plt.plot(
    benchmark[date_col],
    benchmark["NAV"],
    linewidth=2,
    label="WLS"
)

plt.title("Bloomberg WLS sur 10 ans")
plt.xlabel("Date")
plt.ylabel("Base 100")
plt.grid(alpha=0.3)
plt.legend()
plt.tight_layout()
plt.show()


# ============================================================
# GRAPH PER OFFSET
# ============================================================

for strategy_name, path in STRATEGIES.items():

    df = pd.read_csv(
        path,
        parse_dates=["date", "end_date"]
    )

    plt.figure(figsize=(13, 6))

    # WLS rebased at start of backtest
    start = df["date"].min()

    bench = benchmark[
        benchmark[date_col] >= start
    ].copy()

    bench["NAV_rebased"] = (
        100
        * bench["NAV"]
        / bench["NAV"].iloc[0]
    )

    plt.plot(
        bench[date_col],
        bench["NAV_rebased"],
        linewidth=2.5,
        label="WLS"
    )

    for offset, sub in df.groupby("offset"):

        sub = sub.sort_values("date").copy()

        sub["NAV"] = (
            100
            * (1 + sub["net_return_5w"]).cumprod()
        )

        # Put NAV value at end of holding period
        plt.plot(
            sub["end_date"],
            sub["NAV"],
            linewidth=1.5,
            label=f"Offset {offset}"
        )

    plt.title(f"{strategy_name} — NAV par offset")
    plt.xlabel("Date")
    plt.ylabel("Valeur du portefeuille (base 100)")
    plt.grid(alpha=0.3)
    plt.legend()

    plt.tight_layout()
    plt.show()