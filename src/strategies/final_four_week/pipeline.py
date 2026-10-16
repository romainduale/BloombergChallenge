from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from src.build_execution_plan import PRICES_PATH, build_plan
from src.combined_signal_v1 import build_combined_signal
from src.features import build_panel, load_bloomberg_data
from src.opportunistic_model import (
    SIGNAL_PATH as OPPORTUNISTIC_SIGNAL_PATH,
)
from src.opportunistic_model import (
    OpportunisticConfig,
    build_opportunistic_portfolio,
    compute_opportunity_scores,
    download_market_history,
    fetch_analyst_upside,
    load_candidates,
    load_config,
    load_latest_fx,
)
from src.refresh_feature_market_data import refresh_market_data
from src.risk_screen_v1 import BENCHMARK_PATH
from src.strategies.final_four_week.config import (
    DEFAULT_STRATEGY_PROFILE,
    StrategyProfile,
    load_strategy_profile,
)
from src.strategies.final_four_week.constants import (
    CHALLENGE_END_DATE,
    COEFFICIENTS_PATH,
    COMBINED_ALLOCATION_PATH,
    CORE_PORTFOLIO_PATH,
    FINAL_CSV_PATH,
    FINAL_SIGNAL_DATE,
    HORIZON_WEEKS,
    MANIFEST_PATH,
    ORDERS_PATH,
    OUTPUT_ROOT,
    PANEL_PATH,
    SIGNAL_PATH,
)
from src.strategies.final_four_week.export import (
    build_final_explained_export,
    write_final_export,
)
from src.strategies.final_four_week.features import create_panel
from src.strategies.final_four_week.models import fit_latest_four_week_models
from src.strategies.final_four_week.portfolio import build_core_portfolio_4w

OPPORTUNISTIC_OUTPUT_DIR = OUTPUT_ROOT / "opportunistic_20"
LEGACY_PANEL_PATH = Path("data/processed/features_weekly_v1.csv.gz")


def combine_80_20(
    core: pd.DataFrame,
    opportunistic: pd.DataFrame,
    config: OpportunisticConfig,
) -> pd.DataFrame:
    """Assemble les poches sans modifier la logique de sélection opportuniste."""

    core_allocated = core.copy()
    core_allocated["weight"] = (
        core_allocated["weight"].astype(float) / core_allocated["weight"].sum()
    ) * config.core_weight
    core_allocated["sleeve"] = "core_4w"
    opportunity_allocated = opportunistic.copy()
    opportunity_allocated["sleeve"] = "opportunistic"
    opportunity_allocated["strategy_profile"] = "opportunistic_unchanged"

    columns = sorted(set(core_allocated).union(opportunity_allocated))
    combined = pd.concat(
        [
            core_allocated.reindex(columns=columns),
            opportunity_allocated.reindex(columns=columns),
        ],
        ignore_index=True,
    )
    if combined["id"].duplicated().any():
        duplicates = combined.loc[combined["id"].duplicated(False), "id"].unique()
        raise ValueError("Titres présents dans les deux poches : " + ", ".join(duplicates))
    if not np.isclose(combined["weight"].sum(), 1.0, atol=1e-8):
        raise ValueError("L'allocation 80/20 ne totalise pas 100 %.")
    if combined["weight"].max() > config.max_global_position_weight + 1e-10:
        raise ValueError("Un titre dépasse le plafond global de 20 %.")
    return combined.sort_values("weight", ascending=False).reset_index(drop=True)


def build_unchanged_opportunistic_sleeve(
    core: pd.DataFrame,
    *,
    skip_analysts: bool,
    period: str,
) -> tuple[pd.DataFrame, dict[str, str | int | float | None]]:
    """Exécute les fonctions existantes de la poche 20 %, sans changer ses paramètres."""

    config = load_config()
    candidates = load_candidates(config)
    prices, volumes = download_market_history(candidates, period=period)
    fx_rates = load_latest_fx()
    scores = compute_opportunity_scores(prices, volumes, candidates, fx_rates, config)

    if not skip_analysts:
        analyst_candidates = scores[scores["eligible"]].head(12).set_index("id")["yahoo_ticker"]
        analyst_upside = fetch_analyst_upside(analyst_candidates)
        scores = compute_opportunity_scores(
            prices,
            volumes,
            candidates,
            fx_rates,
            config,
            analyst_upside=analyst_upside,
        )

    core_ids = set(core.loc[core["weight"].gt(0.005), "id"])
    opportunistic = build_opportunistic_portfolio(scores, core_ids, config)
    OPPORTUNISTIC_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(OPPORTUNISTIC_OUTPUT_DIR / "candidate_universe.csv", index=False)
    prices.to_csv(OPPORTUNISTIC_OUTPUT_DIR / "yfinance_prices.csv", index_label="date")
    volumes.to_csv(OPPORTUNISTIC_OUTPUT_DIR / "yfinance_volumes.csv", index_label="date")
    scores.to_csv(OPPORTUNISTIC_OUTPUT_DIR / "opportunity_scores.csv", index=False)
    opportunistic.to_csv(OPPORTUNISTIC_OUTPUT_DIR / "opportunistic_portfolio.csv", index=False)
    latest_market_date = prices.apply(lambda series: series.last_valid_index()).max()
    metadata: dict[str, str | int | float | None] = {
        "latest_market_date": (
            None if pd.isna(latest_market_date) else str(pd.Timestamp(latest_market_date).date())
        ),
        "eligible_candidates": int(scores["eligible"].sum()),
        "selected_positions": int(len(opportunistic)),
        "skip_analysts": skip_analysts,
        "candidate_signal_date": str(pd.Timestamp(candidates["date"].max()).date()),
    }
    return opportunistic, metadata


def refresh_opportunistic_upstream_signal() -> pd.DataFrame:
    """Actualise l'entrée cinq semaines historique sans changer la stratégie 20 %."""

    prices, volumes, benchmark = load_bloomberg_data()
    legacy_panel = build_panel(prices, volumes, benchmark)
    LEGACY_PANEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    legacy_panel.to_csv(LEGACY_PANEL_PATH, index=False, compression="gzip")
    legacy_signal = build_combined_signal()
    OPPORTUNISTIC_SIGNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    legacy_signal.to_csv(OPPORTUNISTIC_SIGNAL_PATH, index=False)
    return legacy_signal


def _last_date(path: Path, column: str = "date") -> pd.Timestamp:
    frame = pd.read_csv(path, usecols=[column], parse_dates=[column])
    return pd.Timestamp(frame[column].max())


def _write_manifest(
    *,
    requested_data_end: pd.Timestamp,
    signal_date: pd.Timestamp,
    opportunistic_metadata: dict[str, str | int | float | None],
    config: OpportunisticConfig,
    strategy_profile: StrategyProfile,
    refresh_enabled: bool,
) -> dict[str, object]:
    price_date = _last_date(PRICES_PATH)
    benchmark_date = _last_date(BENCHMARK_PATH)
    planned_exit_date = signal_date + pd.Timedelta(weeks=HORIZON_WEEKS)
    manifest: dict[str, object] = {
        "strategy": "final_four_week_80_20",
        "strategy_profile": asdict(strategy_profile),
        "requested_data_end": str(requested_data_end.date()),
        "market_refresh_enabled": refresh_enabled,
        "prices_through": str(price_date.date()),
        "benchmark_through": str(benchmark_date.date()),
        "signal_date": str(signal_date.date()),
        "horizon_weeks": HORIZON_WEEKS,
        "planned_exit_date": str(planned_exit_date.date()),
        "challenge_end_date": str(CHALLENGE_END_DATE.date()),
        "challenge_aligned": planned_exit_date == CHALLENGE_END_DATE,
        "allocation": {"core": config.core_weight, "opportunistic": config.opportunistic_weight},
        "opportunistic_config_unchanged": asdict(config),
        "opportunistic_data": opportunistic_metadata,
        "outputs": {
            "panel": str(PANEL_PATH),
            "signal": str(SIGNAL_PATH),
            "coefficients": str(COEFFICIENTS_PATH),
            "core_portfolio": str(CORE_PORTFOLIO_PATH),
            "combined_allocation": str(COMBINED_ALLOCATION_PATH),
            "orders": str(ORDERS_PATH),
            "final_csv": str(FINAL_CSV_PATH),
        },
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pipeline finale : cœur 80 % à quatre semaines et poche 20 % inchangée."
    )
    parser.add_argument("--capital", type=float, default=1_000_000.0)
    parser.add_argument("--profile", default="sans_stop")
    parser.add_argument(
        "--strategy-profile",
        choices=["prudent", "intermediaire", "agressif"],
        default=DEFAULT_STRATEGY_PROFILE,
        help="Profil de sélection et d'optimisation du cœur 80 %%.",
    )
    parser.add_argument("--current-positions", type=Path)
    parser.add_argument(
        "--refresh-market-data",
        action="store_true",
        help="Télécharge les prix/volumes jusqu'à --data-end avant le calcul.",
    )
    parser.add_argument(
        "--data-end",
        type=pd.Timestamp,
        default=pd.Timestamp.today().normalize(),
        help="Dernière date demandée à Yahoo, incluse (aujourd'hui par défaut).",
    )
    parser.add_argument(
        "--require-signal-date",
        type=pd.Timestamp,
        default=FINAL_SIGNAL_DATE,
        help=(
            "Arrête la pipeline si le dernier vendredi disponible ne correspond pas "
            f"(défaut : {FINAL_SIGNAL_DATE.date()})."
        ),
    )
    parser.add_argument("--skip-analysts", action="store_true")
    parser.add_argument("--opportunistic-period", default="2y")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    strategy_profile = load_strategy_profile(args.strategy_profile)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    if args.refresh_market_data:
        print(f"Actualisation des prix et volumes jusqu'au {args.data_end.date()}...")
        refresh_market_data(end=args.data_end)

    print("Construction de la cible quatre semaines...")
    panel = create_panel(PANEL_PATH)
    print("Entraînement Elastic Net et Tail avec diagnostics...")
    model_result = fit_latest_four_week_models(panel, strategy_profile=strategy_profile)
    model_result.ranking.to_csv(SIGNAL_PATH, index=False)
    model_result.coefficients.to_csv(COEFFICIENTS_PATH, index=False)
    signal_date = pd.Timestamp(model_result.ranking["date"].max())
    if args.require_signal_date is not None:
        expected = pd.Timestamp(args.require_signal_date).normalize()
        if signal_date.normalize() != expected:
            raise RuntimeError(
                "Signal incomplet : dernier vendredi "
                f"{signal_date.date()}, attendu {expected.date()}."
            )

    print("Construction du portefeuille cœur 80 % à quatre semaines...")
    core, covariance, correlation = build_core_portfolio_4w(
        model_result.ranking,
        strategy_profile=strategy_profile,
    )
    core.to_csv(CORE_PORTFOLIO_PATH, index=False)
    covariance.to_csv(OUTPUT_ROOT / "ledoit_wolf_excess_covariance_weekly.csv")
    correlation.to_csv(OUTPUT_ROOT / "ledoit_wolf_excess_correlation.csv")

    print("Actualisation du signal historique utilisé par la poche 20 %...")
    refresh_opportunistic_upstream_signal()
    print("Calcul de la poche opportuniste 20 % avec ses règles inchangées...")
    opportunistic, opportunistic_metadata = build_unchanged_opportunistic_sleeve(
        core,
        skip_analysts=args.skip_analysts,
        period=args.opportunistic_period,
    )
    config = load_config()
    combined = combine_80_20(core, opportunistic, config)
    combined.to_csv(COMBINED_ALLOCATION_PATH, index=False)

    print("Construction des ordres et du CSV final explicable...")
    orders, _ = build_plan(
        COMBINED_ALLOCATION_PATH,
        args.current_positions,
        args.profile,
        args.capital,
    )
    orders.to_csv(ORDERS_PATH, index=False)
    final_export = build_final_explained_export(
        combined,
        orders,
        model_result.ranking,
        capital=args.capital,
    )
    write_final_export(final_export)
    manifest = _write_manifest(
        requested_data_end=args.data_end,
        signal_date=signal_date,
        opportunistic_metadata=opportunistic_metadata,
        config=config,
        strategy_profile=strategy_profile,
        refresh_enabled=args.refresh_market_data,
    )

    print("\nPipeline finale terminée.")
    print(f"Signal : {manifest['signal_date']}")
    print(f"Sortie prévue : {manifest['planned_exit_date']}")
    print(f"Aligné sur le 13 novembre : {manifest['challenge_aligned']}")
    print(f"CSV final : {FINAL_CSV_PATH}")
    if manifest["benchmark_through"] < manifest["prices_through"]:
        print(
            "ATTENTION : le benchmark WLS est moins récent que les prix. "
            "Importe l'export Bloomberg via src.weekly_data_update pour le mettre à jour."
        )


if __name__ == "__main__":
    main()
