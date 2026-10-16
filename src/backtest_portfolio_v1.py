from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.linear_model import ElasticNet, LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.covariance import estimate_ledoit_wolf
from src.elastic_net_transversal import (
    FEATURES,
    TARGET,
    ElasticNetConfig,
    load_panel,
)
from src.robust_optimizer_v1 import (
    HORIZON_WEEKS,
    KAPPA,
    MAX_WEIGHT,
    portfolio_risk,
)

PRICES_PATH = Path("data/bloomberg/data/prices_10y.csv.gz")

BENCHMARK_PATH = Path("data/bloomberg/data/benchmark_10y.csv")

OUTPUT_DIR = Path("data/processed/portfolio_backtest")

TAIL_WEIGHT = 0.75
ELASTIC_WEIGHT = 0.25

TOP_N = 30
SHORTLIST_SIZE = 12
MAX_CORRELATION = 0.80

LOOKBACK_WEEKS = 52
MIN_RISK_OBSERVATIONS = 40

# V1 :
# un seul calendrier de périodes
# non chevauchantes de 5 semaines.
OFFSET = 0


def prepare_data(
    panel: pd.DataFrame,
) -> pd.DataFrame:
    data = panel.dropna(subset=FEATURES + [TARGET]).copy()

    # À chaque date historique :
    # top 10 % des futures surperformances = 1.
    threshold = data.groupby("date")[TARGET].transform(lambda x: x.quantile(0.90))

    data["tail_target"] = (data[TARGET] >= threshold).astype(int)

    return data


def make_elastic_model(
    config: ElasticNetConfig,
) -> Pipeline:
    return Pipeline(
        [
            (
                "scaler",
                StandardScaler(),
            ),
            (
                "model",
                ElasticNet(
                    alpha=config.alpha,
                    l1_ratio=config.l1_ratio,
                    max_iter=10000,
                ),
            ),
        ]
    )


def make_tail_model() -> Pipeline:
    return Pipeline(
        [
            (
                "scaler",
                StandardScaler(),
            ),
            (
                "model",
                LogisticRegression(
                    C=1.0,
                    solver="lbfgs",
                    max_iter=1000,
                    class_weight="balanced",
                    l1_ratio=0,
                ),
            ),
        ]
    )


def get_test_dates(
    data: pd.DataFrame,
    config: ElasticNetConfig,
) -> pd.DatetimeIndex:
    dates = pd.DatetimeIndex(sorted(pd.to_datetime(data["date"].unique())))

    first_test_date = (
        dates.min()
        + pd.DateOffset(years=config.train_years)
        + pd.Timedelta(weeks=config.purge_weeks)
    )

    eligible = dates[dates >= first_test_date]

    return eligible[OFFSET :: config.test_every_n_weeks]


def load_market_history() -> tuple[
    pd.DataFrame,
    pd.Series,
]:
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

    weekly_prices = prices.resample("W-FRI").last()

    weekly_benchmark = benchmark.resample("W-FRI").last()

    return (
        weekly_prices,
        weekly_benchmark,
    )


def covariance_to_correlation(
    covariance: pd.DataFrame,
) -> pd.DataFrame:
    array = covariance.to_numpy()

    std = np.sqrt(np.diag(array))

    denominator = np.outer(
        std,
        std,
    )

    correlation = np.divide(
        array,
        denominator,
        out=np.zeros_like(array),
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


def estimate_historical_risk(
    test_date: pd.Timestamp,
    candidate_ids: list[str],
    weekly_prices: pd.DataFrame,
    weekly_benchmark: pd.Series,
) -> pd.DataFrame:
    available = [asset for asset in candidate_ids if asset in weekly_prices.columns]

    prices = weekly_prices.loc[
        :test_date,
        available,
    ].tail(LOOKBACK_WEEKS + 1)

    benchmark = weekly_benchmark.loc[:test_date].tail(LOOKBACK_WEEKS + 1)

    stock_returns = prices.pct_change(fill_method=None)

    benchmark_returns = benchmark.pct_change(fill_method=None)

    excess_returns = stock_returns.sub(
        benchmark_returns,
        axis=0,
    )

    result = estimate_ledoit_wolf(
        excess_returns,
        min_observations=(MIN_RISK_OBSERVATIONS),
    )

    return result.covariance_weekly


def build_shortlist(
    ranking: pd.DataFrame,
    covariance: pd.DataFrame,
    *,
    max_correlation: float = MAX_CORRELATION,
    shortlist_size: int = SHORTLIST_SIZE,
) -> pd.DataFrame:
    correlation = covariance_to_correlation(covariance)

    ranking = ranking[ranking["id"].isin(correlation.columns)]

    selected = []

    for _, row in ranking.iterrows():
        asset = row["id"]

        if not selected:
            accepted = True

        else:
            maximum = float(
                correlation.loc[
                    asset,
                    selected,
                ]
                .abs()
                .max()
            )

            accepted = maximum <= max_correlation

        if accepted:
            selected.append(asset)

        if len(selected) >= shortlist_size:
            break

    return ranking[ranking["id"].isin(selected)].copy().head(shortlist_size)


def optimise(
    shortlist: pd.DataFrame,
    covariance: pd.DataFrame,
    horizon_weeks: int = HORIZON_WEEKS,
    *,
    kappa: float = KAPPA,
    max_weight: float = MAX_WEIGHT,
) -> np.ndarray:
    assets = shortlist["id"].tolist()

    alpha = shortlist["elastic_prediction"].to_numpy(dtype=float)

    covariance_horizon = (
        covariance.loc[
            assets,
            assets,
        ].to_numpy(dtype=float)
        * horizon_weeks
    )

    n_assets = len(assets)

    initial_weights = np.repeat(
        1.0 / n_assets,
        n_assets,
    )

    def objective(
        weights: np.ndarray,
    ) -> float:
        expected_alpha = float(alpha @ weights)

        risk = portfolio_risk(
            weights,
            covariance_horizon,
        )

        return -(expected_alpha - kappa * risk)

    result = minimize(
        objective,
        initial_weights,
        method="SLSQP",
        bounds=[
            (
                0.0,
                max_weight,
            )
            for _ in range(n_assets)
        ],
        constraints=[
            {
                "type": "eq",
                "fun": lambda w: np.sum(w) - 1.0,
            }
        ],
        options={
            "maxiter": 5000,
            "ftol": 1e-12,
        },
    )

    if not result.success:
        raise RuntimeError(result.message)

    return result.x


def benchmark_future_return(
    date: pd.Timestamp,
    weekly_benchmark: pd.Series,
    horizon_weeks: int = HORIZON_WEEKS,
) -> float:
    dates = weekly_benchmark.index

    if date not in dates:
        return np.nan

    location = dates.get_loc(date)

    future_location = location + horizon_weeks

    if future_location >= len(dates):
        return np.nan

    start = float(weekly_benchmark.iloc[location])

    end = float(weekly_benchmark.iloc[future_location])

    return end / start - 1.0


def max_drawdown(
    returns: pd.Series,
) -> float:
    wealth = (1.0 + returns).cumprod()

    running_max = wealth.cummax()

    drawdown = wealth / running_max - 1.0

    return float(drawdown.min())


def main():
    config = ElasticNetConfig()

    print("Chargement des données...")

    panel = load_panel()

    panel["date"] = pd.to_datetime(panel["date"])

    data = prepare_data(panel)

    (
        weekly_prices,
        weekly_benchmark,
    ) = load_market_history()

    test_dates = get_test_dates(
        data,
        config,
    )

    rows = []

    print("\n")
    print("=" * 72)
    print("BACKTEST PORTEFEUILLE COMPLET V1")
    print("=" * 72)

    for number, test_date in enumerate(
        test_dates,
        start=1,
    ):
        train_end = test_date - pd.Timedelta(weeks=config.purge_weeks)

        train_start = train_end - pd.DateOffset(years=config.train_years)

        train = data[(data["date"] >= train_start) & (data["date"] < train_end)].copy()

        test = data[data["date"] == test_date].copy()

        if len(train) < config.min_train_rows:
            continue

        if len(test) < config.min_test_rows:
            continue

        elastic = make_elastic_model(config)

        tail = make_tail_model()

        elastic.fit(
            train[FEATURES],
            train[TARGET],
        )

        tail.fit(
            train[FEATURES],
            train["tail_target"],
        )

        test["elastic_prediction"] = elastic.predict(test[FEATURES])

        test["tail_score"] = tail.predict_proba(test[FEATURES])[:, 1]

        test["elastic_rank"] = test["elastic_prediction"].rank(
            pct=True,
            method="average",
        )

        test["tail_rank"] = test["tail_score"].rank(
            pct=True,
            method="average",
        )

        test["combined_score"] = (
            TAIL_WEIGHT * test["tail_rank"] + ELASTIC_WEIGHT * test["elastic_rank"]
        )

        ranking = (
            test.sort_values(
                "combined_score",
                ascending=False,
            )
            .head(TOP_N)
            .copy()
        )

        try:
            covariance = estimate_historical_risk(
                test_date,
                ranking["id"].tolist(),
                weekly_prices,
                weekly_benchmark,
            )

        except ValueError:
            print(f"[{number}/{len(test_dates)}] {test_date.date()} | risque insuffisant → ignoré")
            continue

        shortlist = build_shortlist(
            ranking,
            covariance,
        )

        if len(shortlist) < 6:
            continue

        weights = optimise(
            shortlist,
            covariance,
        )

        realised_excess = shortlist[TARGET].to_numpy(dtype=float)

        robust_excess = float(weights @ realised_excess)

        equal_weights = np.repeat(
            1.0 / len(shortlist),
            len(shortlist),
        )

        equal_excess = float(equal_weights @ realised_excess)

        benchmark_return = benchmark_future_return(
            test_date,
            weekly_benchmark,
        )

        if np.isnan(benchmark_return):
            continue

        robust_absolute = benchmark_return + robust_excess

        equal_absolute = benchmark_return + equal_excess

        relative_period_return = (1.0 + robust_absolute) / (1.0 + benchmark_return) - 1.0

        rows.append(
            {
                "date": test_date,
                "n_test": len(test),
                "n_shortlist": (len(shortlist)),
                "robust_excess_5w": (robust_excess),
                "equal_excess_5w": (equal_excess),
                "benchmark_return_5w": (benchmark_return),
                "robust_return_5w": (robust_absolute),
                "equal_return_5w": (equal_absolute),
                "relative_wealth_return": (relative_period_return),
                "max_weight": float(weights.max()),
                "n_positions_gt_1pct": int(np.sum(weights >= 0.01)),
            }
        )

        print(
            f"[{number}/"
            f"{len(test_dates)}] "
            f"{test_date.date()} "
            f"| alpha réalisé="
            f"{robust_excess:+.2%} "
            f"| EW="
            f"{equal_excess:+.2%}"
        )

    results = pd.DataFrame(rows)

    if results.empty:
        raise RuntimeError("Aucune période de backtest n'a été produite.")

    robust_wealth = (1.0 + results["robust_return_5w"]).cumprod()

    benchmark_wealth = (1.0 + results["benchmark_return_5w"]).cumprod()

    equal_wealth = (1.0 + results["equal_return_5w"]).cumprod()

    final_relative = float(robust_wealth.iloc[-1] / benchmark_wealth.iloc[-1] - 1.0)

    equal_final_relative = float(equal_wealth.iloc[-1] / benchmark_wealth.iloc[-1] - 1.0)

    print("\n")
    print("=" * 72)
    print("RÉSULTATS BACKTEST V1")
    print("=" * 72)

    print(f"Nombre de périodes : {len(results)}")

    print(
        "Surperformance moyenne "
        "par période de 5 semaines : "
        f"{results['robust_excess_5w'].mean():+.2%}"
    )

    print(f"Surperformance médiane : {results['robust_excess_5w'].median():+.2%}")

    print(f"% périodes où on bat le WLS : {(results['robust_excess_5w'] > 0).mean():.1%}")

    print(f"Equal-weight surperformance moyenne : {results['equal_excess_5w'].mean():+.2%}")

    print(f"Surperformance cumulée Robust vs WLS : {final_relative:+.2%}")

    print(f"Surperformance cumulée Equal Weight vs WLS : {equal_final_relative:+.2%}")

    print(f"Max drawdown portefeuille : {max_drawdown(results['robust_return_5w']):.2%}")

    print(f"Max drawdown WLS : {max_drawdown(results['benchmark_return_5w']):.2%}")

    print(f"Poids maximum moyen : {results['max_weight'].mean():.2%}")

    print(f"Nombre moyen de positions >1% : {results['n_positions_gt_1pct'].mean():.1f}")

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    results.to_csv(
        OUTPUT_DIR / "portfolio_backtest_v1.csv",
        index=False,
    )

    print("\nFichier créé : data/processed/portfolio_backtest/portfolio_backtest_v1.csv")


if __name__ == "__main__":
    main()
