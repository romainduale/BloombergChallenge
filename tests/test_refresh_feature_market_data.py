from pathlib import Path

import pandas as pd

from src.refresh_feature_market_data import (
    RefreshConfig,
    load_yahoo_mapping,
    merge_validated_history,
    refresh_market_data,
    validate_download,
)


def test_mapping_marks_duplicate_yahoo_symbols(tmp_path: Path):
    universe_path = tmp_path / "universe.csv"
    pd.DataFrame(
        {
            "id": ["A UN Equity", "A UW Equity", "NESN SE Equity"],
            "ticker_exchange": ["A UN", "A UW", "NESN SE"],
        }
    ).to_csv(universe_path, index=False)

    mapping = load_yahoo_mapping(
        pd.Index(["A UN Equity", "A UW Equity", "NESN SE Equity"]),
        universe_path=universe_path,
        override_path=tmp_path / "absent.csv",
    ).set_index("id")

    assert mapping.loc["A UN Equity", "mapping_status"] == "DUPLICATE_YAHOO_TICKER"
    assert mapping.loc["A UW Equity", "mapping_status"] == "DUPLICATE_YAHOO_TICKER"
    assert mapping.loc["NESN SE Equity", "yahoo_ticker"] == "NESN.SW"
    assert mapping.loc["NESN SE Equity", "mapping_status"] == "READY"


def test_validation_rejects_wrong_mapping_and_merge_keeps_original_history():
    dates = pd.to_datetime(["2026-10-05", "2026-10-06", "2026-10-07"])
    existing = pd.DataFrame({"GOOD": [100.0, 101.0, 102.0], "BAD": [50.0, 51.0, 52.0]}, index=dates)
    downloaded = pd.DataFrame(
        {
            "GOOD": [101.0, 102.0, 103.0, 104.0],
            "BAD": [102.0, 104.0, 106.0, 108.0],
        },
        index=pd.to_datetime(["2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09"]),
    )
    mapping = pd.DataFrame(
        {
            "id": ["GOOD", "BAD"],
            "ticker_exchange": ["GOOD UN", "BAD UN"],
            "yahoo_ticker": ["GOOD", "BAD"],
            "mapping_status": ["READY", "READY"],
        }
    )
    report = validate_download(
        existing,
        downloaded,
        mapping,
        last_source_date=pd.Timestamp("2026-10-07"),
        config=RefreshConfig(maximum_median_relative_error=0.02),
    )
    status = report.set_index("id")["refresh_status"]

    assert status["GOOD"] == "VALIDATED"
    assert status["BAD"] == "OVERLAP_MISMATCH"

    merged = merge_validated_history(
        existing,
        downloaded,
        report,
        last_source_date=pd.Timestamp("2026-10-07"),
    )
    assert merged.loc[pd.Timestamp("2026-10-07"), "GOOD"] == 102.0
    assert merged.loc[pd.Timestamp("2026-10-09"), "GOOD"] == 104.0
    assert pd.isna(merged.loc[pd.Timestamp("2026-10-09"), "BAD"])


def test_refresh_is_idempotent_when_requested_date_is_already_present(tmp_path: Path):
    dates = pd.to_datetime(["2026-10-07", "2026-10-08"])
    prices_path = tmp_path / "prices.csv.gz"
    volumes_path = tmp_path / "volumes.csv.gz"
    report_path = tmp_path / "report.csv"
    pd.DataFrame({"A UN Equity": [100.0, 101.0]}, index=dates).rename_axis("date").to_csv(
        prices_path, compression="gzip"
    )
    pd.DataFrame({"A UN Equity": [10.0, 11.0]}, index=dates).rename_axis("date").to_csv(
        volumes_path, compression="gzip"
    )
    pd.DataFrame(
        {
            "id": ["A UN Equity"],
            "refresh_status": ["VALIDATED"],
            "latest_download_date": ["2026-10-08"],
        }
    ).to_csv(report_path, index=False)

    report = refresh_market_data(
        end=pd.Timestamp("2026-10-08"),
        prices_path=prices_path,
        volumes_path=volumes_path,
        universe_path=tmp_path / "unused.csv",
        mapping_path=tmp_path / "unused_mapping.csv",
        report_path=report_path,
    )

    assert report.loc[0, "refresh_status"] == "VALIDATED"
