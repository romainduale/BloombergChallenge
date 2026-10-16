from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from src.execution_rules import build_execution_orders
from src.market_metadata import infer_currency
from src.trading_config import load_execution_profile

PRICES_PATH = Path("data/bloomberg/data/prices_10y.csv.gz")
STATIC_PATH = Path("data/bloomberg/data/static.csv")
FX_PATH = Path("data/bloomberg/data/fx_rates.csv")
PORTFOLIO_PATH = Path("data/processed/portfolio/portfolio_robust_v1.csv")
OUTPUT_PATH = Path("data/processed/execution/execution_orders.csv")


def load_current_positions(path: Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame(columns=["id", "weight", "entry_price"])
    positions = pd.read_csv(path)
    required = {"id", "weight"}
    missing = required - set(positions.columns)
    if missing:
        raise ValueError(f"Colonnes manquantes dans les positions : {sorted(missing)}")
    if "entry_price" not in positions:
        positions["entry_price"] = np.nan
    return positions[["id", "weight", "entry_price"]]


def load_price_to_usd_rates(
    assets: pd.Index,
    as_of: pd.Timestamp,
    *,
    static_path: Path = STATIC_PATH,
    fx_path: Path = FX_PATH,
) -> pd.Series:
    rates = pd.Series(np.nan, index=assets, dtype=float)
    if not static_path.exists() or not fx_path.exists():
        return rates

    static = pd.read_csv(static_path)
    fx = pd.read_csv(fx_path, parse_dates=["date"])
    if "id" not in static.columns:
        return rates
    if not {"date", "currency", "usd_rate"}.issubset(fx.columns):
        return rates

    fx = fx[fx["date"] <= as_of].copy()
    fx["currency"] = fx["currency"].astype(str).str.upper()
    fx["usd_rate"] = pd.to_numeric(fx["usd_rate"], errors="coerce")
    latest_fx = fx.sort_values("date").drop_duplicates("currency", keep="last")
    currency_rates = latest_fx.set_index("currency")["usd_rate"]
    currency_rates.loc["USD"] = 1.0

    currency_by_asset = pd.Series(index=assets, dtype="string")
    if "currency" in static.columns:
        provided = (
            static.drop_duplicates("id", keep="last")
            .set_index("id")["currency"]
            .astype("string")
            .str.strip()
            .str.upper()
            .replace("", pd.NA)
        )
        currency_by_asset = provided.reindex(assets)
    inferred = pd.Series(
        {asset: infer_currency(asset) for asset in assets},
        dtype="string",
    )
    currency_by_asset = currency_by_asset.fillna(inferred)
    mapped = currency_by_asset.map(currency_rates)
    return mapped.astype(float)


def build_plan(
    portfolio_path: Path,
    positions_path: Path | None,
    profile: str,
    capital: float,
) -> tuple[pd.DataFrame, pd.Timestamp]:
    portfolio = pd.read_csv(portfolio_path)
    if not {"id", "weight"}.issubset(portfolio.columns):
        raise ValueError("Le portefeuille doit contenir les colonnes id et weight.")

    config = load_execution_profile(profile)
    target = portfolio.set_index("id")["weight"].astype(float)
    if target.max() > config.max_position_weight + 1e-8:
        raise ValueError("Le portefeuille dépasse le plafond global de 20 % par actif.")
    if not np.isclose(target.sum(), 1.0, atol=1e-6):
        raise ValueError("Les poids cibles doivent totaliser 100 %.")

    positions = load_current_positions(positions_path)
    current = positions.set_index("id")["weight"].astype(float)
    entries = positions.set_index("id")["entry_price"].astype(float)

    prices = pd.read_csv(PRICES_PATH, parse_dates=["date"]).set_index("date").sort_index()
    assets = target.index.union(current.index)
    available = [asset for asset in assets if asset in prices.columns]
    missing_assets = sorted(set(assets) - set(available))
    if missing_assets:
        raise ValueError("Prix absents pour : " + ", ".join(missing_assets))

    recent = prices[available].dropna(how="all")
    as_of = pd.Timestamp(recent.index.max())
    last_prices = recent.ffill().loc[as_of]
    daily_volatilities = (
        recent.pct_change(fill_method=None)
        .rolling(config.volatility_lookback_days, min_periods=config.volatility_lookback_days)
        .std()
        .iloc[-1]
    )
    price_to_usd_rates = load_price_to_usd_rates(assets, as_of)

    orders = build_execution_orders(
        target,
        current,
        last_prices,
        config,
        as_of=as_of,
        capital=capital,
        entry_prices=entries,
        daily_volatilities=daily_volatilities,
        price_to_usd_rates=price_to_usd_rates,
    )
    orders.insert(0, "as_of", as_of)
    orders.insert(1, "profile", profile)
    return orders, as_of


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Construit les ordres indicatifs du portefeuille.")
    parser.add_argument("--portfolio", type=Path, default=PORTFOLIO_PATH)
    parser.add_argument("--current-positions", type=Path)
    parser.add_argument(
        "--profile",
        default="sans_stop",
        help="Profil d'exécution; sans_stop reste le défaut tant que le stop n'est pas validé.",
    )
    parser.add_argument("--capital", type=float, default=1_000_000.0)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    orders, as_of = build_plan(
        args.portfolio,
        args.current_positions,
        args.profile,
        args.capital,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    orders.to_csv(args.output, index=False)
    print(f"Plan d'exécution au {as_of.date()} : {args.output}")
    print(orders.to_string(index=False))


if __name__ == "__main__":
    main()
