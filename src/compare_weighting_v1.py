from pathlib import Path

import pandas as pd

PATH = Path("data/processed/portfolio_backtest/portfolio_5_offsets_results.csv")


def max_drawdown(returns):
    wealth = (1 + returns).cumprod()
    peak = wealth.cummax()
    return (wealth / peak - 1).min()


def main():
    df = pd.read_csv(
        PATH,
        parse_dates=["date"],
    )

    rows = []

    for offset, group in df.groupby("offset"):
        group = group.sort_values("date")

        robust = group["robust_return_5w"]
        equal = group["equal_return_5w"]

        rows.append(
            {
                "offset": offset,
                "robust_mean": robust.mean(),
                "equal_mean": equal.mean(),
                "robust_vol": robust.std(),
                "equal_vol": equal.std(),
                "robust_drawdown": max_drawdown(robust),
                "equal_drawdown": max_drawdown(equal),
                "robust_beats_equal_pct": (
                    group["robust_excess_5w"] > group["equal_excess_5w"]
                ).mean(),
            }
        )

    result = pd.DataFrame(rows)

    print("\n")
    print("=" * 90)
    print("ROBUST VS EQUAL WEIGHT")
    print("=" * 90)

    print(result.to_string(index=False))

    print("\nMOYENNE DES 5 OFFSETS")

    print(f"Vol Robust : {result['robust_vol'].mean():.2%}")

    print(f"Vol Equal : {result['equal_vol'].mean():.2%}")

    print(f"Drawdown Robust : {result['robust_drawdown'].mean():.2%}")

    print(f"Drawdown Equal : {result['equal_drawdown'].mean():.2%}")

    print(f"Robust bat Equal en moyenne : {result['robust_beats_equal_pct'].mean():.1%}")


if __name__ == "__main__":
    main()
