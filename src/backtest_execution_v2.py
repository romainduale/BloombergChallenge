from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest_portfolio_v1 import (
    TOP_N,
    benchmark_future_return,
    build_shortlist,
    estimate_historical_risk,
    load_market_history,
    make_elastic_model,
    make_tail_model,
    optimise,
)
from src.elastic_net_transversal import FEATURES as V1_FEATURES
from src.elastic_net_transversal import TARGET, ElasticNetConfig
from src.execution_rules import simulate_limit_buy, simulate_stop_loss
from src.features_v2 import V2_FEATURES
from src.trading_config import ExecutionConfig, load_execution_profile
from src.transaction_costs import calculate_turnover

PRICES_PATH = Path("data/bloomberg/data/prices_10y.csv.gz")
PANEL_V1_PATH = Path("data/processed/features_weekly_v1.csv.gz")
PANEL_V2_PATH = Path("data/processed/features_weekly_v2.csv.gz")
OUTPUT_DIR = Path("data/processed/execution_backtest")


def prepare_data(
    panel: pd.DataFrame,
    features: list[str],
    target_column: str = TARGET,
) -> pd.DataFrame:
    data = panel.dropna(subset=features + [target_column]).copy()
    data["date"] = pd.to_datetime(data["date"])
    threshold = data.groupby("date")[target_column].transform(lambda values: values.quantile(0.90))
    data["tail_target"] = data[target_column].ge(threshold).astype(int)
    return data


def get_test_dates(
    data: pd.DataFrame,
    config: ElasticNetConfig,
    offset: int,
) -> pd.DatetimeIndex:
    dates = pd.DatetimeIndex(sorted(data["date"].unique()))
    first_test_date = (
        dates.min()
        + pd.DateOffset(years=config.train_years)
        + pd.Timedelta(weeks=config.purge_weeks)
    )
    return dates[dates >= first_test_date][offset :: config.test_every_n_weeks]


def _period_end(
    date: pd.Timestamp,
    weekly_benchmark: pd.Series,
    horizon_weeks: int = 5,
) -> pd.Timestamp | None:
    if date not in weekly_benchmark.index:
        return None
    location = weekly_benchmark.index.get_loc(date)
    future_location = location + horizon_weeks
    if future_location >= len(weekly_benchmark):
        return None
    return pd.Timestamp(weekly_benchmark.index[future_location])


def run_offset(
    offset: int,
    data: pd.DataFrame,
    features: list[str],
    model_config: ElasticNetConfig,
    execution_config: ExecutionConfig,
    daily_prices: pd.DataFrame,
    weekly_prices: pd.DataFrame,
    weekly_benchmark: pd.Series,
    *,
    target_column: str = TARGET,
    horizon_weeks: int = 5,
    tail_weight: float = 0.75,
    elastic_weight: float = 0.25,
    top_n: int = TOP_N,
    shortlist_size: int = 12,
    max_correlation: float = 0.80,
    kappa: float = 0.15,
    max_position_weight: float = 0.20,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    period_rows = []
    holding_rows = []
    previous_weights = pd.Series(dtype=float)
    previous_cash = 1.0

    for test_date in get_test_dates(data, model_config, offset):
        train_end = test_date - pd.Timedelta(weeks=model_config.purge_weeks)
        train_start = train_end - pd.DateOffset(years=model_config.train_years)
        train = data[(data["date"] >= train_start) & (data["date"] < train_end)]
        test = data[data["date"] == test_date].copy()
        if len(train) < model_config.min_train_rows or len(test) < model_config.min_test_rows:
            continue

        elastic = make_elastic_model(model_config)
        tail = make_tail_model()
        elastic.fit(train[features], train[target_column])
        tail.fit(train[features], train["tail_target"])
        test["elastic_prediction"] = elastic.predict(test[features])
        test["tail_score"] = tail.predict_proba(test[features])[:, 1]
        test["elastic_rank"] = test["elastic_prediction"].rank(pct=True)
        test["tail_rank"] = test["tail_score"].rank(pct=True)
        test["combined_score"] = (
            tail_weight * test["tail_rank"] + elastic_weight * test["elastic_rank"]
        )
        ranking = test.sort_values("combined_score", ascending=False).head(top_n).copy()

        try:
            covariance = estimate_historical_risk(
                test_date,
                ranking["id"].tolist(),
                weekly_prices,
                weekly_benchmark,
            )
        except ValueError:
            continue

        shortlist = build_shortlist(
            ranking,
            covariance,
            max_correlation=max_correlation,
            shortlist_size=shortlist_size,
        )
        minimum_assets = int(np.ceil(1.0 / max_position_weight))
        if len(shortlist) < max(6, minimum_assets):
            continue

        weights = optimise(
            shortlist,
            covariance,
            horizon_weeks=horizon_weeks,
            kappa=kappa,
            max_weight=max_position_weight,
        )
        target_weights = pd.Series(weights, index=shortlist["id"], dtype=float)
        if target_weights.max() > execution_config.max_position_weight + 1e-8:
            raise RuntimeError("L'optimiseur a dépassé le plafond de poids configuré.")

        end_date = _period_end(test_date, weekly_benchmark, horizon_weeks=horizon_weeks)
        benchmark_return = benchmark_future_return(
            test_date,
            weekly_benchmark,
            horizon_weeks=horizon_weeks,
        )
        if end_date is None or np.isnan(benchmark_return):
            continue

        turnover = calculate_turnover(
            previous_weights,
            target_weights,
            execution_config,
            previous_cash_weight=previous_cash,
            target_cash_weight=0.0,
        )

        asset_returns = {}
        stopped_assets = []
        stopped_notional = 0.0
        limit_candidates = 0
        limit_fills = 0
        period_holding_rows = []

        for asset, weight in target_weights.items():
            if asset not in daily_prices.columns:
                continue
            stop = simulate_stop_loss(
                daily_prices[asset],
                pd.Timestamp(test_date),
                end_date,
                execution_config,
            )
            asset_returns[asset] = stop.realised_return
            if stop.stopped:
                stopped_assets.append(asset)
                stopped_notional += float(weight * (1.0 + stop.realised_return))

            previous_weight = float(previous_weights.get(asset, 0.0))
            if weight - previous_weight >= execution_config.minimum_trade_weight:
                limit_candidates += 1
                limit = simulate_limit_buy(
                    daily_prices[asset],
                    pd.Timestamp(test_date),
                    execution_config,
                )
                limit_fills += int(limit.filled)
            else:
                limit = None

            period_holding_rows.append(
                {
                    "offset": offset,
                    "date": test_date,
                    "end_date": end_date,
                    "id": asset,
                    "target_weight": float(weight),
                    "realised_return": stop.realised_return,
                    "stopped": stop.stopped,
                    "stop_distance": stop.stop_distance,
                    "stop_price": stop.stop_price,
                    "stop_trigger_date": stop.trigger_date,
                    "exit_date": stop.exit_date,
                    "exit_price": stop.exit_price,
                    "limit_candidate": limit is not None,
                    "limit_filled": None if limit is None else limit.filled,
                    "limit_price": None if limit is None else limit.limit_price,
                    "limit_fill_date": None if limit is None else limit.fill_date,
                }
            )

        realised = pd.Series(asset_returns, dtype=float).reindex(target_weights.index)
        if realised.isna().any():
            continue

        holding_rows.extend(period_holding_rows)

        gross_return = float(target_weights @ realised)
        stop_cost = stopped_notional * execution_config.total_cost_bps / 10_000.0
        total_cost = turnover.transaction_cost_return + stop_cost
        net_return = gross_return - total_cost

        period_rows.append(
            {
                "offset": offset,
                "date": test_date,
                "end_date": end_date,
                f"gross_return_{horizon_weeks}w": gross_return,
                f"net_return_{horizon_weeks}w": net_return,
                f"benchmark_return_{horizon_weeks}w": benchmark_return,
                f"gross_excess_{horizon_weeks}w": gross_return - benchmark_return,
                f"net_excess_{horizon_weeks}w": net_return - benchmark_return,
                "one_way_turnover": turnover.one_way_turnover,
                "traded_notional": turnover.traded_notional,
                "rebalance_cost_return": turnover.transaction_cost_return,
                "stop_cost_return": stop_cost,
                "total_cost_return": total_cost,
                "n_stops": len(stopped_assets),
                "stopped_weight": float(target_weights.reindex(stopped_assets).sum()),
                "limit_candidates": limit_candidates,
                "limit_fills": limit_fills,
                "limit_fill_rate": (
                    np.nan if limit_candidates == 0 else limit_fills / limit_candidates
                ),
                "max_weight": float(target_weights.max()),
                "n_positions": int(target_weights.gt(1e-6).sum()),
            }
        )

        ending_values = target_weights * (1.0 + realised)
        ending_cash = 0.0
        if stopped_assets:
            ending_cash = float(ending_values.reindex(stopped_assets).sum())
            ending_values.loc[stopped_assets] = 0.0
        gross_ending_value = float(ending_values.sum() + ending_cash)
        previous_weights = ending_values / gross_ending_value
        previous_cash = ending_cash / gross_ending_value

    return pd.DataFrame(period_rows), pd.DataFrame(holding_rows)


def run_backtest(
    panel: pd.DataFrame,
    features: list[str],
    execution_config: ExecutionConfig,
    model_config: ElasticNetConfig | None = None,
    *,
    target_column: str = TARGET,
    horizon_weeks: int = 5,
    tail_weight: float = 0.75,
    elastic_weight: float = 0.25,
    top_n: int = TOP_N,
    shortlist_size: int = 12,
    max_correlation: float = 0.80,
    kappa: float = 0.15,
    max_position_weight: float = 0.20,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    cfg = model_config or ElasticNetConfig()
    data = prepare_data(panel, features, target_column=target_column)
    daily_prices = pd.read_csv(PRICES_PATH, parse_dates=["date"]).set_index("date").sort_index()
    weekly_prices, weekly_benchmark = load_market_history()

    periods = []
    holdings = []
    for offset in range(cfg.test_every_n_weeks):
        result, positions = run_offset(
            offset,
            data,
            features,
            cfg,
            execution_config,
            daily_prices,
            weekly_prices,
            weekly_benchmark,
            target_column=target_column,
            horizon_weeks=horizon_weeks,
            tail_weight=tail_weight,
            elastic_weight=elastic_weight,
            top_n=top_n,
            shortlist_size=shortlist_size,
            max_correlation=max_correlation,
            kappa=kappa,
            max_position_weight=max_position_weight,
        )
        periods.append(result)
        holdings.append(positions)

    return pd.concat(periods, ignore_index=True), pd.concat(holdings, ignore_index=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest avec coûts et règles d'exécution.")
    parser.add_argument("--profile", default="sans_stop")
    parser.add_argument("--feature-set", choices=["v1", "v2"], default="v1")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    panel_path = PANEL_V1_PATH if args.feature_set == "v1" else PANEL_V2_PATH
    features = V1_FEATURES if args.feature_set == "v1" else V2_FEATURES
    panel = pd.read_csv(panel_path, parse_dates=["date"])
    execution_config = load_execution_profile(args.profile)
    periods, holdings = run_backtest(panel, features, execution_config)
    if periods.empty:
        raise RuntimeError("Aucune période de backtest n'a été produite.")

    output = OUTPUT_DIR / f"{args.feature_set}_{args.profile}"
    output.mkdir(parents=True, exist_ok=True)
    periods.to_csv(output / "periods.csv", index=False)
    holdings.to_csv(output / "holdings.csv", index=False)
    print(f"Résultats : {output}")
    print(f"Périodes : {len(periods)}")
    print(f"Surperformance nette moyenne : {periods['net_excess_5w'].mean():+.2%}")
    print(f"Turnover one-way moyen : {periods['one_way_turnover'].mean():.2%}")
    print(f"Coût moyen : {periods['total_cost_return'].mean():.3%}")


if __name__ == "__main__":
    main()
