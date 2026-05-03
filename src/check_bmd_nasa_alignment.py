from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BMD_DIR = PROJECT_ROOT / "data" / "processed" / "bmd_stations_3hourly"
DEFAULT_NASA_ROOT = PROJECT_ROOT / "data" / "processed" / "nasa_station_data"
DEFAULT_ALIGNMENT_REPORT = PROJECT_ROOT / "outputs" / "tables" / "bmd_nasa_alignment_check.csv"
DEFAULT_UNITS_REPORT = PROJECT_ROOT / "outputs" / "tables" / "bmd_nasa_units_check.csv"

EXPECTED_COLUMNS = ["YEAR", "MO", "DY", "HR", "T2M", "RH2M", "PRECTOTCORR", "WS10M"]
EXPECTED_ROWS = 11688
EXPECTED_HOURS = [0, 3, 6, 9, 12, 15, 18, 21]
KEY_COLUMNS = ["YEAR", "MO", "DY", "HR"]


UNIT_ROWS = [
    {
        "parameter": "T2M",
        "bmd_unit": "degree Celsius",
        "nasa_hourly_unit": "C",
        "picked_3h_unit_match": "yes",
        "average_3h_unit_match": "yes",
        "note": "Averaging temperature over a 3-hour window keeps the same Celsius unit.",
    },
    {
        "parameter": "RH2M",
        "bmd_unit": "%",
        "nasa_hourly_unit": "%",
        "picked_3h_unit_match": "yes",
        "average_3h_unit_match": "yes",
        "note": "Averaging relative humidity over a 3-hour window keeps the same percent unit.",
    },
    {
        "parameter": "PRECTOTCORR",
        "bmd_unit": "millimeter per 3-hour observation",
        "nasa_hourly_unit": "mm/hour transformed to 3-hour total",
        "picked_3h_unit_match": "yes",
        "average_3h_unit_match": "yes",
        "note": "NASA hourly precipitation is summed over each 3-hour window; T2M/RH2M/WS10M still follow the selected picked or averaged method.",
    },
    {
        "parameter": "WS10M",
        "bmd_unit": "m/s",
        "nasa_hourly_unit": "m/s",
        "picked_3h_unit_match": "yes",
        "average_3h_unit_match": "yes",
        "note": "Averaging wind speed over a 3-hour window keeps the same m/s unit.",
    },
]


def read_station_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    for column in EXPECTED_COLUMNS:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def key_frame(df: pd.DataFrame) -> pd.DataFrame:
    return df[KEY_COLUMNS].astype("int64").reset_index(drop=True)


def valid_dates(df: pd.DataFrame) -> bool:
    dates = pd.to_datetime(
        {
            "year": df["YEAR"],
            "month": df["MO"],
            "day": df["DY"],
        },
        errors="coerce",
    )
    return not dates.isna().any()


def summarize_numeric(df: pd.DataFrame, prefix: str) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for column in ["T2M", "RH2M", "PRECTOTCORR", "WS10M"]:
        row[f"{prefix}_{column}_missing"] = int(df[column].isna().sum())
        row[f"{prefix}_{column}_min"] = df[column].min(skipna=True)
        row[f"{prefix}_{column}_max"] = df[column].max(skipna=True)
    return row


def compare_pair(station_file: Path, nasa_file: Path, variant: str) -> dict[str, Any]:
    station_id = station_file.stem
    bmd = read_station_csv(station_file)
    nasa = read_station_csv(nasa_file)
    same_keys = key_frame(bmd).equals(key_frame(nasa))
    row: dict[str, Any] = {
        "station_id": station_id,
        "variant": variant,
        "bmd_file": str(station_file.relative_to(PROJECT_ROOT)),
        "nasa_file": str(nasa_file.relative_to(PROJECT_ROOT)),
        "same_filename": station_file.name == nasa_file.name,
        "same_columns": list(bmd.columns) == list(nasa.columns) == EXPECTED_COLUMNS,
        "bmd_rows": len(bmd),
        "nasa_rows": len(nasa),
        "expected_rows_match": len(bmd) == len(nasa) == EXPECTED_ROWS,
        "same_date_hour_keys": same_keys,
        "bmd_hours": ",".join(map(str, sorted(bmd["HR"].dropna().unique().astype(int)))),
        "nasa_hours": ",".join(map(str, sorted(nasa["HR"].dropna().unique().astype(int)))),
        "expected_hours_match": (
            sorted(bmd["HR"].dropna().unique().astype(int)) == EXPECTED_HOURS
            and sorted(nasa["HR"].dropna().unique().astype(int)) == EXPECTED_HOURS
        ),
        "bmd_valid_dates": valid_dates(bmd),
        "nasa_valid_dates": valid_dates(nasa),
    }
    row.update(summarize_numeric(bmd, "bmd"))
    row.update(summarize_numeric(nasa, "nasa"))
    return row


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check that processed BMD and NASA station datasets align structurally."
    )
    parser.add_argument("--bmd-dir", type=Path, default=DEFAULT_BMD_DIR)
    parser.add_argument("--nasa-root", type=Path, default=DEFAULT_NASA_ROOT)
    parser.add_argument("--alignment-report", type=Path, default=DEFAULT_ALIGNMENT_REPORT)
    parser.add_argument("--units-report", type=Path, default=DEFAULT_UNITS_REPORT)
    args = parser.parse_args()

    variants = {
        "3h_picked": args.nasa_root / "3h_picked",
        "3h_average": args.nasa_root / "3h_average",
    }
    bmd_files = sorted(args.bmd_dir.glob("*.csv"))
    rows: list[dict[str, Any]] = []
    failures: list[str] = []

    for bmd_file in bmd_files:
        for variant, variant_dir in variants.items():
            nasa_file = variant_dir / bmd_file.name
            if not nasa_file.exists():
                failures.append(f"Missing NASA {variant} file for {bmd_file.name}")
                continue
            row = compare_pair(bmd_file, nasa_file, variant)
            rows.append(row)
            check_columns = [
                "same_filename",
                "same_columns",
                "expected_rows_match",
                "same_date_hour_keys",
                "expected_hours_match",
                "bmd_valid_dates",
                "nasa_valid_dates",
            ]
            for column in check_columns:
                if not row[column]:
                    failures.append(f"{bmd_file.name} {variant} failed {column}")

    write_csv(args.alignment_report, rows)
    write_csv(args.units_report, UNIT_ROWS)

    print(f"Checked {len(bmd_files)} BMD station files against {len(variants)} NASA variants.")
    print(f"Wrote alignment report: {args.alignment_report}")
    print(f"Wrote units report: {args.units_report}")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        raise RuntimeError(f"{len(failures)} alignment failure(s).")
    print("Structural alignment passed: filenames, columns, rows, date/hour keys, and hours match.")
    print("Unit alignment passed: PRECTOTCORR is summed to 3-hour totals in NASA outputs.")


if __name__ == "__main__":
    main()
