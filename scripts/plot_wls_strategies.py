from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ============================================================
# PATHS
# ============================================================

BENCHMARK_PATH = Path("data/bloomberg/data/benchmark_10y.csv")

STRATEGIES = {
    "Sans stop": Path(
        "data/processed/execution_backtest/v1_sans_stop/periods.csv"
    ),
    "Stop fixe": Path(
        "data/processed/execution_backtest/v1_stop_fixe/periods.csv"
    ),
    "Stop volatilité": Path(
        "data/processed/execution_backtest/v1_equilibre/periods.csv"
    ),
}


# ============================================================
# HELPERS
# ============================================================

def find_column(df, candidates):
    """Return first existing candidate column."""
    for col in candidates:
        if col in df.columns:
            return col
    return None


def cumulative_nav(returns):
    """NAV starting at 100."""
    returns = pd.to_numeric(returns, errors="coerce").fillna(0.0)
    return 100.0 * (1.0 + returns).cumprod()


# ============================================================
# WLS BENCHMARK
# ============================================================

benchmark = pd.read_csv(BENCHMARK_PATH)

print("\n=== Colonnes benchmark ===")
print(list(benchmark.columns))

date_col = find_column(
    benchmark,
    ["date", "Date", "DATE"]
)

if date_col is None:
    raise ValueError(
        f"Impossible de trouver la date dans le benchmark : "
        f"{list(benchmark.columns)}"
    )

benchmark[date_col] = pd.to_datetime(benchmark[date_col])
benchmark = benchmark.sort_values(date_col)


# ------------------------------------------------------------
# Try price/index level first
# ------------------------------------------------------------

level_col = find_column(
    benchmark,
    [
        "price",
        "Price",
        "PX_LAST",
        "px_last",
        "close",
        "Close",
        "value",
        "Value",
        "index_value",
        "benchmark_value",
        "wls"
    ]
)

return_col = find_column(
    benchmark,
    [
        "return",
        "Return",
        "ret",
        "benchmark_return",
        "wls_return",
        "daily_return"
    ]
)


if level_col is not None:

    benchmark[level_col] = pd.to_numeric(
        benchmark[level_col],
        errors="coerce"
    )

    benchmark = benchmark.dropna(
        subset=[date_col, level_col]
    )

    benchmark["WLS_NAV"] = (
        100.0
        * benchmark[level_col]
        / benchmark[level_col].iloc[0]
    )

elif return_col is not None:

    benchmark["WLS_NAV"] = cumulative_nav(
        benchmark[return_col]
    )

else:
    raise ValueError(
        "Je ne trouve ni niveau d'indice ni rendement dans benchmark_10y.csv.\n"
        f"Colonnes disponibles : {list(benchmark.columns)}"
    )


# ============================================================
# STRATEGIES
# ============================================================

strategy_curves = {}

for strategy_name, path in STRATEGIES.items():

    df = pd.read_csv(path)

    print(f"\n=== Colonnes {strategy_name} ===")
    print(list(df.columns))

    df["date"] = pd.to_datetime(df["date"])

    if "end_date" in df.columns:
        df["end_date"] = pd.to_datetime(df["end_date"])

    # --------------------------------------------------------
    # Find offset
    # --------------------------------------------------------

    offset_col = find_column(
        df,
        ["offset", "calendar_offset", "rebalance_offset"]
    )

    # --------------------------------------------------------
    # Find portfolio net return
    # --------------------------------------------------------

    portfolio_return_col = find_column(
        df,
        [
            "net_portfolio_return",
            "portfolio_net_return",
            "net_return",
            "net_return_5w",
            "portfolio_return_net",
            "strategy_return",
            "portfolio_return"
        ]
    )

    # --------------------------------------------------------
    # If only excess return exists, reconstruct strategy return
    # using benchmark return.
    # --------------------------------------------------------

    excess_col = find_column(
        df,
        [
            "net_excess_return",
            "net_excess_return_5w",
            "net_excess_5w",
            "excess_return_net",
            "relative_return_net"
        ]
    )

    bench_col = find_column(
        df,
        [
            "benchmark_return",
            "benchmark_return_5w",
            "wls_return",
            "wls_return_5w"
        ]
    )

    if portfolio_return_col is not None:

        df["_strategy_return"] = pd.to_numeric(
            df[portfolio_return_col],
            errors="coerce"
        )

    elif excess_col is not None and bench_col is not None:

        df["_strategy_return"] = (
            pd.to_numeric(df[bench_col], errors="coerce")
            + pd.to_numeric(df[excess_col], errors="coerce")
        )

    else:
        raise ValueError(
            f"\nImpossible de reconstruire le rendement de {strategy_name}.\n"
            f"Colonnes disponibles : {list(df.columns)}"
        )

    # --------------------------------------------------------
    # Each offset is a separate non-overlapping portfolio path.
    # Build NAV per offset, then average the normalized NAVs.
    # --------------------------------------------------------

    if offset_col is not None:

        curves = []

        for offset, sub in df.groupby(offset_col):

            sub = sub.sort_values("date").copy()

            sub["NAV"] = cumulative_nav(
                sub["_strategy_return"]
            )

            curve = sub[
                ["date", "NAV"]
            ].rename(
                columns={"NAV": f"NAV_{offset}"}
            )

            curves.append(curve)

        combined = curves[0]

        for curve in curves[1:]:
            combined = combined.merge(
                curve,
                on="date",
                how="outer"
            )

        combined = combined.sort_values("date")

        nav_cols = [
            c for c in combined.columns
            if c.startswith("NAV_")
        ]

        combined["NAV"] = combined[nav_cols].mean(
            axis=1,
            skipna=True
        )

        strategy_curves[strategy_name] = combined[
            ["date", "NAV"]
        ].dropna()

    else:

        df = df.sort_values("date").copy()

        df["NAV"] = cumulative_nav(
            df["_strategy_return"]
        )

        strategy_curves[strategy_name] = df[
            ["date", "NAV"]
        ].dropna()


# ============================================================
# GRAPH 1
# WLS OVER FULL 10 YEARS
# ============================================================

plt.figure(figsize=(13, 6))

plt.plot(
    benchmark[date_col],
    benchmark["WLS_NAV"],
    linewidth=2,
    label="WLS"
)

plt.xlabel("Date")
plt.ylabel("Valeur normalisée (base 100)")
plt.title("Évolution du Bloomberg WLS sur 10 ans")

plt.grid(alpha=0.3)
plt.legend()

plt.tight_layout()
plt.show()


# ============================================================
# GRAPH 2
# WLS + STRATEGIES FROM COMMON START
# ============================================================

strategy_start = min(
    curve["date"].min()
    for curve in strategy_curves.values()
)

bench_common = benchmark[
    benchmark[date_col] >= strategy_start
].copy()

if bench_common.empty:
    raise ValueError("Aucune donnée WLS sur la période du backtest.")

# rebase WLS to 100 at strategy start
bench_common["WLS_REBASED"] = (
    100.0
    * bench_common["WLS_NAV"]
    / bench_common["WLS_NAV"].iloc[0]
)


plt.figure(figsize=(14, 7))

plt.plot(
    bench_common[date_col],
    bench_common["WLS_REBASED"],
    linewidth=2.5,
    label="WLS"
)


for strategy_name, curve in strategy_curves.items():

    curve = curve[
        curve["date"] >= strategy_start
    ].copy()

    if curve.empty:
        continue

    curve["NAV_REBASED"] = (
        100.0
        * curve["NAV"]
        / curve["NAV"].iloc[0]
    )

    plt.plot(
        curve["date"],
        curve["NAV_REBASED"],
        linewidth=2,
        label=strategy_name
    )


plt.xlabel("Date")
plt.ylabel("Valeur du portefeuille (base 100)")
plt.title(
    "WLS vs stratégies du Bloomberg Trading Challenge"
)

plt.grid(alpha=0.3)
plt.legend()

plt.tight_layout()
plt.show()