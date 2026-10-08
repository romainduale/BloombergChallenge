from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from src.elastic_net_transversal import (
    FEATURES,
    TARGET,
    ElasticNetConfig,
    calculate_rank_ic,
    load_panel,
    make_model,
    prepare_training_data,
)

OUTPUT_DIR = Path("data/processed/validation")


def get_test_dates(
    data: pd.DataFrame,
    config: ElasticNetConfig,
    offset: int,
) -> pd.DatetimeIndex:
    """
    Construit les dates de test pour un décalage donné.

    Avec test_every_n_weeks = 5 :

    offset 0 : semaine 1, 6, 11, 16...
    offset 1 : semaine 2, 7, 12, 17...
    offset 2 : semaine 3, 8, 13, 18...
    etc.
    """

    if offset < 0 or offset >= config.test_every_n_weeks:
        raise ValueError("offset invalide")

    dates = pd.DatetimeIndex(sorted(data["date"].unique()))

    first_test_date = (
        dates.min()
        + pd.DateOffset(years=config.train_years)
        + pd.Timedelta(weeks=config.purge_weeks)
    )

    eligible_dates = dates[dates >= first_test_date]

    return eligible_dates[offset :: config.test_every_n_weeks]


def run_schedule(
    data: pd.DataFrame,
    config: ElasticNetConfig,
    offset: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Entraîne et teste l'Elastic Net
    sur un calendrier donné.

    Retourne :
    - les IC de chaque période ;
    - les coefficients appris par le modèle.
    """

    test_dates = get_test_dates(
        data,
        config,
        offset,
    )

    ic_rows = []
    coefficient_rows = []

    print(f"\nOffset {offset} | {len(test_dates)} dates potentielles")

    for number, test_date in enumerate(
        test_dates,
        start=1,
    ):
        train_end = test_date - pd.Timedelta(weeks=config.purge_weeks)

        train_start = train_end - pd.DateOffset(years=config.train_years)

        train = data[(data["date"] >= train_start) & (data["date"] < train_end)]

        test = data[data["date"] == test_date]

        if len(train) < config.min_train_rows:
            continue

        if len(test) < config.min_test_rows:
            continue

        X_train = train[FEATURES]
        y_train = train[TARGET]

        X_test = test[FEATURES]
        y_test = test[TARGET]

        model = make_model(config)

        model.fit(
            X_train,
            y_train,
        )

        predictions = model.predict(X_test)

        ic = calculate_rank_ic(
            y_test,
            predictions,
        )

        ic_rows.append(
            {
                "date": test_date,
                "offset": offset,
                "ic": ic,
                "n_train": len(train),
                "n_test": len(test),
            }
        )

        elastic_net = model.named_steps["elastic_net"]

        coefficient_row = {
            "date": test_date,
            "offset": offset,
        }

        for feature, coefficient in zip(
            FEATURES,
            elastic_net.coef_,
            strict=True,
        ):
            coefficient_row[feature] = coefficient

        coefficient_rows.append(coefficient_row)

        if number == 1 or number % 10 == 0 or number == len(test_dates):
            print(f"[{number}/{len(test_dates)}] {test_date.date()} | IC={ic:.4f}")

    return (
        pd.DataFrame(ic_rows),
        pd.DataFrame(coefficient_rows),
    )


def summarize_ic(
    ic_df: pd.DataFrame,
) -> dict[str, float]:
    """
    Résume les performances
    d'un ensemble d'IC.
    """

    values = ic_df["ic"].dropna()

    return {
        "n_periods": len(values),
        "mean_ic": values.mean(),
        "median_ic": values.median(),
        "positive_ic_pct": (values > 0).mean(),
        "std_ic": values.std(),
    }


def newey_west_mean_test(
    values: pd.Series,
    max_lag: int = 4,
) -> dict[str, float]:
    """
    Teste si la moyenne des IC est différente de zéro.

    On corrige l'autocorrélation liée au fait
    que nos rendements futurs couvrent 5 semaines.

    max_lag = 4 :
    les observations peuvent être dépendantes
    sur les 4 semaines suivantes.
    """

    x = values.dropna().to_numpy(dtype=float)

    n = len(x)

    if n < 10:
        raise ValueError("Pas assez d'observations.")

    mean = x.mean()

    residuals = x - mean

    gamma_0 = (residuals @ residuals) / n

    long_run_variance = gamma_0

    for lag in range(
        1,
        max_lag + 1,
    ):
        weight = 1 - lag / (max_lag + 1)

        gamma_lag = (residuals[lag:] @ residuals[:-lag]) / n

        long_run_variance += 2 * weight * gamma_lag

    standard_error = np.sqrt(long_run_variance / n)

    if standard_error > 0:
        t_stat = mean / standard_error
    else:
        t_stat = np.nan

    return {
        "mean_ic": mean,
        "hac_standard_error": standard_error,
        "hac_t_stat": t_stat,
        "n": n,
    }


def run_offset_validation(
    data: pd.DataFrame,
    config: ElasticNetConfig,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Teste les 5 calendriers possibles
    du walk-forward.
    """

    all_ic = []
    all_coefficients = []
    summary_rows = []

    print("\n")
    print("=" * 60)
    print("TEST DES 5 DÉCALAGES")
    print("=" * 60)

    for offset in range(config.test_every_n_weeks):
        (
            ic_df,
            coefficients_df,
        ) = run_schedule(
            data,
            config,
            offset,
        )

        summary = summarize_ic(ic_df)

        summary["offset"] = offset

        summary_rows.append(summary)

        all_ic.append(ic_df)

        all_coefficients.append(coefficients_df)

    ic_all = pd.concat(
        all_ic,
        ignore_index=True,
    )

    ic_all = ic_all.sort_values("date").reset_index(drop=True)

    coefficients_all = pd.concat(
        all_coefficients,
        ignore_index=True,
    )

    summary_df = pd.DataFrame(summary_rows)

    columns = [
        "offset",
        "n_periods",
        "mean_ic",
        "median_ic",
        "positive_ic_pct",
        "std_ic",
    ]

    summary_df = summary_df[columns]

    print("\n")
    print(summary_df.to_string(index=False))

    print("\n")
    print(f"IC moyen sur toutes les dates : {ic_all['ic'].mean():.4f}")

    # ========================================================
    # IC PAR ANNÉE
    # ========================================================

    ic_by_year = (
        ic_all.assign(year=pd.to_datetime(ic_all["date"]).dt.year)
        .groupby("year")["ic"]
        .agg(
            [
                "count",
                "mean",
                "median",
                "std",
            ]
        )
    )

    print("\n")
    print("=" * 60)
    print("IC PAR ANNÉE")
    print("=" * 60)

    print(ic_by_year.to_string())

    # ========================================================
    # SIGNIFICATIVITÉ NEWEY-WEST / HAC
    # ========================================================

    statistical_test = newey_west_mean_test(
        ic_all["ic"],
        max_lag=4,
    )

    print("\n")
    print("=" * 60)
    print("SIGNIFICATIVITÉ DU SIGNAL")
    print("=" * 60)

    print(f"Nombre d'observations : {statistical_test['n']}")

    print(f"IC moyen : {statistical_test['mean_ic']:.4f}")

    print(f"Erreur standard HAC : {statistical_test['hac_standard_error']:.4f}")

    print(f"t-stat HAC : {statistical_test['hac_t_stat']:.2f}")

    return (
        summary_df,
        ic_all,
        coefficients_all,
    )


def summarize_coefficients(
    coefficients_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Analyse ce que l'Elastic Net apprend.

    Comme les variables sont standardisées,
    les coefficients sont plus facilement
    comparables.
    """

    rows = []

    for feature in FEATURES:
        values = coefficients_df[feature].dropna()

        rows.append(
            {
                "feature": feature,
                "mean_coefficient": (values.mean()),
                "median_coefficient": (values.median()),
                "std_coefficient": (values.std()),
                "positive_pct": (values > 0).mean(),
                "negative_pct": (values < 0).mean(),
                "zero_pct": (values == 0).mean(),
            }
        )

    result = pd.DataFrame(rows)

    result["abs_mean_coefficient"] = result["mean_coefficient"].abs()

    result = result.sort_values(
        "abs_mean_coefficient",
        ascending=False,
    )

    return result


def shuffle_target_within_date(
    data: pd.DataFrame,
    seed: int,
) -> pd.DataFrame:
    """
    Crée notre test placebo.

    Pour chaque date, on mélange
    les rendements futurs entre les actions.

    La distribution des rendements reste identique,
    mais le lien entre les features
    et le rendement futur est détruit.
    """

    rng = np.random.default_rng(seed)

    placebo = data.copy()

    groups = placebo.groupby(
        "date",
        sort=False,
    ).groups

    for indices in groups.values():
        index_list = list(indices)

        values = placebo.loc[
            index_list,
            TARGET,
        ].to_numpy(copy=True)

        placebo.loc[
            index_list,
            TARGET,
        ] = rng.permutation(values)

    return placebo


def run_placebo_validation(
    data: pd.DataFrame,
    config: ElasticNetConfig,
) -> pd.DataFrame:
    """
    Entraîne plusieurs fois le modèle
    sur des targets mélangées.

    Si notre pipeline est sain :

        IC placebo ≈ 0
    """

    seeds = [
        101,
        202,
        303,
    ]

    summary_rows = []

    print("\n")
    print("=" * 60)
    print("TEST PLACEBO")
    print("=" * 60)

    for seed in seeds:
        print(f"\nPlacebo seed={seed}")

        placebo_data = shuffle_target_within_date(
            data,
            seed,
        )

        (
            ic_df,
            _,
        ) = run_schedule(
            placebo_data,
            config,
            offset=0,
        )

        summary = summarize_ic(ic_df)

        summary["seed"] = seed

        summary_rows.append(summary)

    placebo_summary = pd.DataFrame(summary_rows)

    columns = [
        "seed",
        "n_periods",
        "mean_ic",
        "median_ic",
        "positive_ic_pct",
        "std_ic",
    ]

    placebo_summary = placebo_summary[columns]

    print("\n")
    print(placebo_summary.to_string(index=False))

    print("\n")
    print("IC moyen des placebos :")

    print(f"{placebo_summary['mean_ic'].mean():.4f}")

    return placebo_summary


def parse_args():
    """
    Permet de choisir quels tests lancer.

    Exemples :

    python -m src.validate_elastic_net --mode offsets

    python -m src.validate_elastic_net --mode placebo

    python -m src.validate_elastic_net --mode all
    """

    parser = argparse.ArgumentParser(
        description=("Validation de l'Elastic Net du Bloomberg Trading Challenge")
    )

    parser.add_argument(
        "--mode",
        choices=[
            "offsets",
            "placebo",
            "all",
        ],
        default="all",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    config = ElasticNetConfig()

    print("Chargement du panel...")

    raw_df = load_panel()

    data = prepare_training_data(raw_df)

    print(f"{len(data):,} observations complètes utilisables.")

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if args.mode in {
        "offsets",
        "all",
    }:
        (
            offset_summary,
            offset_ic,
            coefficients,
        ) = run_offset_validation(
            data,
            config,
        )

        coefficient_summary = summarize_coefficients(coefficients)

        print("\n")
        print("=" * 60)
        print("COEFFICIENTS ELASTIC NET")
        print("=" * 60)

        print(coefficient_summary.to_string(index=False))

        offset_summary.to_csv(
            OUTPUT_DIR / "offset_summary.csv",
            index=False,
        )

        offset_ic.to_csv(
            OUTPUT_DIR / "offset_ic.csv",
            index=False,
        )

        coefficients.to_csv(
            OUTPUT_DIR / "coefficients_by_date.csv",
            index=False,
        )

        coefficient_summary.to_csv(
            OUTPUT_DIR / "coefficient_summary.csv",
            index=False,
        )

    if args.mode in {
        "placebo",
        "all",
    }:
        placebo_summary = run_placebo_validation(
            data,
            config,
        )

        placebo_summary.to_csv(
            OUTPUT_DIR / "placebo_summary.csv",
            index=False,
        )


if __name__ == "__main__":
    main()
