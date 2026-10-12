from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.trading_config import ExecutionConfig


@dataclass(frozen=True)
class StopSimulation:
    realised_return: float
    stopped: bool
    stop_distance: float | None
    stop_price: float | None
    trigger_date: pd.Timestamp | None
    exit_date: pd.Timestamp
    exit_price: float


@dataclass(frozen=True)
class LimitSimulation:
    filled: bool
    fill_date: pd.Timestamp | None
    fill_price: float | None
    limit_price: float


def historical_daily_volatility(
    prices: pd.Series,
    as_of: pd.Timestamp,
    lookback_days: int,
) -> float:
    history = prices.loc[:as_of].dropna().tail(lookback_days + 1)
    returns = history.pct_change(fill_method=None).dropna()
    if len(returns) < lookback_days:
        return np.nan
    return float(returns.std(ddof=1))


def stop_distance(
    config: ExecutionConfig,
    *,
    daily_volatility: float | None = None,
) -> float | None:
    if config.stop_loss_mode == "none":
        return None
    if config.stop_loss_mode == "fixed":
        return config.fixed_stop_loss_pct
    if daily_volatility is None or not np.isfinite(daily_volatility):
        return config.fixed_stop_loss_pct

    raw_distance = config.volatility_multiplier * daily_volatility * np.sqrt(5.0)
    return float(np.clip(raw_distance, config.minimum_stop_pct, config.maximum_stop_pct))


def simulate_stop_loss(
    prices: pd.Series,
    entry_date: pd.Timestamp,
    end_date: pd.Timestamp,
    config: ExecutionConfig,
) -> StopSimulation:
    series = prices.sort_index().dropna()
    entry_candidates = series.loc[entry_date:]
    if entry_candidates.empty:
        raise ValueError("Aucun prix disponible à partir de la date d'entrée.")

    actual_entry_date = pd.Timestamp(entry_candidates.index[0])
    entry_price = float(entry_candidates.iloc[0])
    holding_path = series.loc[actual_entry_date:end_date]
    if holding_path.empty:
        raise ValueError("Aucun prix disponible pendant la période de détention.")

    daily_vol = historical_daily_volatility(
        series,
        actual_entry_date,
        config.volatility_lookback_days,
    )
    distance = stop_distance(config, daily_volatility=daily_vol)

    if distance is not None:
        stop_price = entry_price * (1.0 - distance)
        breaches = holding_path.iloc[1:][holding_path.iloc[1:] <= stop_price]
    else:
        stop_price = None
        breaches = pd.Series(dtype=float)

    if not breaches.empty:
        trigger_date = pd.Timestamp(breaches.index[0])
        trigger_location = holding_path.index.get_loc(trigger_date)
        exit_location = min(
            trigger_location + config.stop_execution_delay_days,
            len(holding_path) - 1,
        )
        exit_date = pd.Timestamp(holding_path.index[exit_location])
        exit_price = float(holding_path.iloc[exit_location])
        stopped = True
    else:
        trigger_date = None
        exit_date = pd.Timestamp(holding_path.index[-1])
        exit_price = float(holding_path.iloc[-1])
        stopped = False

    return StopSimulation(
        realised_return=exit_price / entry_price - 1.0,
        stopped=stopped,
        stop_distance=distance,
        stop_price=stop_price,
        trigger_date=trigger_date,
        exit_date=exit_date,
        exit_price=exit_price,
    )


def simulate_limit_buy(
    prices: pd.Series,
    decision_date: pd.Timestamp,
    config: ExecutionConfig,
) -> LimitSimulation:
    series = prices.sort_index().dropna()
    reference_candidates = series.loc[:decision_date]
    if reference_candidates.empty:
        raise ValueError("Aucun prix disponible avant la décision.")

    reference_price = float(reference_candidates.iloc[-1])
    limit_price = reference_price * (1.0 - config.limit_discount_pct)
    future = series.loc[decision_date:].iloc[1 : config.limit_valid_days + 1]
    fills = future[future <= limit_price]

    if fills.empty:
        return LimitSimulation(False, None, None, limit_price)

    return LimitSimulation(
        filled=True,
        fill_date=pd.Timestamp(fills.index[0]),
        fill_price=limit_price,
        limit_price=limit_price,
    )


def build_execution_orders(
    target_weights: pd.Series,
    current_weights: pd.Series,
    last_prices: pd.Series,
    config: ExecutionConfig,
    *,
    as_of: pd.Timestamp,
    capital: float = 1_000_000.0,
    entry_prices: pd.Series | None = None,
    daily_volatilities: pd.Series | None = None,
    price_to_usd_rates: pd.Series | None = None,
) -> pd.DataFrame:
    if capital <= 0:
        raise ValueError("Le capital doit être strictement positif.")

    assets = target_weights.index.union(current_weights.index)
    target = target_weights.reindex(assets, fill_value=0.0).astype(float)
    current = current_weights.reindex(assets, fill_value=0.0).astype(float)
    prices = last_prices.reindex(assets).astype(float)
    entries = (
        pd.Series(dtype=float).reindex(assets)
        if entry_prices is None
        else entry_prices.reindex(assets).astype(float)
    )
    volatilities = (
        pd.Series(dtype=float).reindex(assets)
        if daily_volatilities is None
        else daily_volatilities.reindex(assets).astype(float)
    )
    fx_rates = (
        pd.Series(dtype=float).reindex(assets)
        if price_to_usd_rates is None
        else price_to_usd_rates.reindex(assets).astype(float)
    )

    if target.max() > config.max_position_weight + 1e-10:
        raise ValueError("Un poids cible dépasse le plafond configuré.")

    rows = []
    for asset in assets:
        price = prices.get(asset, np.nan)
        if not np.isfinite(price) or price <= 0:
            raise ValueError(f"Prix invalide pour {asset}.")

        delta = float(target[asset] - current[asset])
        entry_price = entries.get(asset, np.nan)
        distance = stop_distance(
            config,
            daily_volatility=volatilities.get(asset, np.nan),
        )
        active_reference = float(entry_price) if np.isfinite(entry_price) else float(price)
        protective_stop = None if distance is None else active_reference * (1.0 - distance)

        stop_triggered = (
            current[asset] > 0 and protective_stop is not None and price <= protective_stop
        )
        if stop_triggered:
            action = "SELL_STOP"
            order_type = "MARKET_SELL"
            trade_weight = -float(current[asset])
        elif target[asset] <= config.minimum_trade_weight and current[asset] > 0:
            action = "SELL"
            order_type = "MARKET_SELL"
            trade_weight = -float(current[asset])
        elif abs(delta) < config.minimum_trade_weight:
            action = "HOLD"
            order_type = "NONE"
            trade_weight = 0.0
        elif delta > 0:
            action = "BUY" if current[asset] == 0 else "INCREASE"
            order_type = "LIMIT_BUY"
            trade_weight = delta
        else:
            action = "REDUCE"
            order_type = "MARKET_SELL"
            trade_weight = delta

        limit_price = (
            price * (1.0 - config.limit_discount_pct) if order_type == "LIMIT_BUY" else np.nan
        )
        validity_date = (
            as_of + pd.offsets.BDay(config.limit_valid_days)
            if order_type == "LIMIT_BUY"
            else pd.NaT
        )
        trade_dollars = trade_weight * capital
        fx_rate = fx_rates.get(asset, np.nan)
        usd_price = price * fx_rate if np.isfinite(fx_rate) and fx_rate > 0 else np.nan
        if trade_weight == 0.0:
            estimated_shares = 0
            share_estimate_status = "NOT_APPLICABLE"
        elif np.isfinite(usd_price):
            estimated_shares = int(np.floor(abs(trade_dollars) / usd_price))
            share_estimate_status = "READY"
        else:
            estimated_shares = pd.NA
            share_estimate_status = "FX_REQUIRED"

        rows.append(
            {
                "id": asset,
                "action": action,
                "order_type": order_type,
                "current_weight": float(current[asset]),
                "target_weight": float(target[asset]),
                "trade_weight": trade_weight,
                "last_price": float(price),
                "limit_price": limit_price,
                "limit_valid_until": validity_date,
                "protective_stop_price": protective_stop,
                "stop_distance": distance,
                "target_allocation_usd": float(target[asset] * capital),
                "trade_allocation_usd": trade_dollars,
                "price_to_usd_rate": fx_rate,
                "estimated_shares": estimated_shares,
                "share_estimate_status": share_estimate_status,
            }
        )

    return pd.DataFrame(rows).sort_values(
        ["order_type", "trade_allocation_usd"],
        ascending=[True, False],
    )
