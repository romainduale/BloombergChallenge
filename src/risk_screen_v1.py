from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.covariance import estimate_ledoit_wolf

COMBINED_PATH = Path("data/processed/combined_signal/latest_combined_signal_v1.csv")

PRICES_PATH = Path("data/bloomberg/data/prices_10y.csv.gz")

BENCHMARK_PATH = Path("data/bloomberg/data/benchmark_10y.csv")

OUTPUT_DIR = Path("data/processed/risk_screen")

TOP_N = 30
LOOKBACK_WEEKS = 52
MIN_OBSERVATIONS = 40
MAX_CORRELATION = 0.80
SHORTLIST_SIZE = 12


def covariance_to_correlation(
    covariance: pd.DataFrame,
) -> pd.DataFrame:
    std = np.sqrt(np.diag(covariance.to_numpy()))

    denominator = np.outer(
        std,
        std,
    )

    correlation = np.divide(
        covariance.to_numpy(),
        denominator,
        out=np.zeros_like(covariance.to_numpy()),
        where=denominator > 0,
    )

    return pd.DataFrame(
        np.clip(
            correlation,
            -1.0,
            1.0,
        ),
        index=covariance.index,
        columns=covariance.columns,
    )


def load_candidates() -> pd.DataFrame:
    candidates = pd.read_csv(
        COMBINED_PATH,
        parse_dates=["date"],
    )

    return (
        candidates.sort_values(
            "combined_score",
            ascending=False,
        )
        .head(TOP_N)
        .reset_index(drop=True)
    )


def build_excess_returns(
    candidates: pd.DataFrame,
) -> pd.DataFrame:
    prices = (
        pd.read_csv(
            PRICES_PATH,
            parse_dates=["date"],
        )
        .set_index("date")
        .sort_index()
    )

    benchmark = (
        pd.read_csv(
            BENCHMARK_PATH,
            parse_dates=["date"],
        )
        .set_index("date")["px_last"]
        .sort_index()
    )

    signal_date = pd.Timestamp(candidates["date"].max())

    ids = [asset for asset in candidates["id"] if asset in prices.columns]

    weekly_prices = (
        prices.loc[
            :signal_date,
            ids,
        ]
        .resample("W-FRI")
        .last()
        .tail(LOOKBACK_WEEKS + 1)
    )

    weekly_benchmark = benchmark.loc[:signal_date].resample("W-FRI").last().tail(LOOKBACK_WEEKS + 1)

    stock_returns = weekly_prices.pct_change(fill_method=None)

    benchmark_returns = weekly_benchmark.pct_change(fill_method=None)

    # Très important :
    # on mesure ici le risque RELATIF au WLS.
    excess_returns = stock_returns.sub(
        benchmark_returns,
        axis=0,
    )

    valid_assets = excess_returns.notna().sum().loc[lambda x: x >= MIN_OBSERVATIONS].index

    excess_returns = excess_returns[valid_assets].dropna(how="any")

    return excess_returns


def strongest_correlations(
    correlation: pd.DataFrame,
    n: int = 15,
) -> pd.DataFrame:
    rows = []

    assets = correlation.columns.tolist()

    for i, asset_1 in enumerate(assets):
        for asset_2 in assets[i + 1 :]:
            value = float(
                correlation.loc[
                    asset_1,
                    asset_2,
                ]
            )

            rows.append(
                {
                    "asset_1": asset_1,
                    "asset_2": asset_2,
                    "correlation": value,
                    "abs_correlation": abs(value),
                }
            )

    return (
        pd.DataFrame(rows)
        .sort_values(
            "abs_correlation",
            ascending=False,
        )
        .head(n)
    )


def build_shortlist(
    candidates: pd.DataFrame,
    correlation: pd.DataFrame,
) -> pd.DataFrame:
    candidates = candidates[candidates["id"].isin(correlation.columns)]

    selected = []
    output = []

    for _, row in candidates.iterrows():
        asset = row["id"]

        if not selected:
            max_corr = 0.0
        else:
            max_corr = float(
                correlation.loc[
                    asset,
                    selected,
                ]
                .abs()
                .max()
            )

        if max_corr <= MAX_CORRELATION:
            selected.append(asset)

            output.append(
                {
                    "id": asset,
                    "combined_score": (row["combined_score"]),
                    "tail_rank": (row["tail_rank"]),
                    "elastic_rank": (row["elastic_rank"]),
                    "predicted_excess_return": (row["predicted_excess_return"]),
                    "max_abs_correlation": (max_corr),
                }
            )

        if len(selected) >= SHORTLIST_SIZE:
            break

    return pd.DataFrame(output)


def main():
    candidates = load_candidates()

    excess_returns = build_excess_returns(candidates)

    result = estimate_ledoit_wolf(
        excess_returns,
        min_observations=(MIN_OBSERVATIONS),
    )

    covariance = result.covariance_weekly

    correlation = covariance_to_correlation(covariance)

    pairs = strongest_correlations(correlation)

    shortlist = build_shortlist(
        candidates,
        correlation,
    )

    print("\n")
    print("=" * 70)
    print("LEDOIT-WOLF - RISQUE RELATIF AU WLS")
    print("=" * 70)

    print(f"Shrinkage : {result.shrinkage:.3f}")

    print(f"Semaines utilisées : {result.n_observations}")

    print("\n")
    print("15 CORRÉLATIONS LES PLUS FORTES")

    print(
        pairs[
            [
                "asset_1",
                "asset_2",
                "correlation",
            ]
        ].to_string(index=False)
    )

    print("\n")
    print("SHORTLIST - 12 CANDIDATS")

    print(shortlist.to_string(index=False))

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    covariance.to_csv(OUTPUT_DIR / "ledoit_wolf_excess_covariance_weekly.csv")

    correlation.to_csv(OUTPUT_DIR / "ledoit_wolf_excess_correlation.csv")

    shortlist.to_csv(
        OUTPUT_DIR / "shortlist_v1.csv",
        index=False,
    )


if __name__ == "__main__":
    main()
