from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATIONS_JSON = PROJECT_ROOT / "data" / "processed" / "bmd_station_coordinates_35.json"
DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw" / "nasa_power"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "processed" / "nasa_station_data"
DEFAULT_REPORT = PROJECT_ROOT / "outputs" / "tables" / "nasa_power_3hourly_processing_report.csv"

START = "20210101"
END = "20241231"
TIME_STANDARD = "UTC"
VALUE_COLUMNS = ["T2M", "RH2M", "PRECTOTCORR", "WS10M"]
AVERAGE_COLUMNS = ["T2M", "RH2M", "WS10M"]
OUTPUT_COLUMNS = ["YEAR", "MO", "DY", "HR", *VALUE_COLUMNS]
OBSERVED_HOURS = [0, 3, 6, 9, 12, 15, 18, 21]
EXPECTED_3H_ROWS = 11688


def load_stations(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    stations = data.get("stations")
    if not isinstance(stations, list):
        raise ValueError(f"{path} must contain a top-level 'stations' list.")
    return stations


def raw_nasa_path(raw_dir: Path, station_id: str, start: str, end: str, time_standard: str) -> Path:
    return raw_dir / f"{station_id}_POWER_Point_Hourly_{start}_{end}_{time_standard}.csv"


def read_hourly_nasa(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = set(OUTPUT_COLUMNS).difference(df.columns)
    if missing:
        raise ValueError(f"{path.name} is missing columns: {', '.join(sorted(missing))}")

    df = df[OUTPUT_COLUMNS].copy()
    for column in OUTPUT_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df["timestamp"] = pd.to_datetime(
        {
            "year": df["YEAR"],
            "month": df["MO"],
            "day": df["DY"],
        },
        errors="raise",
    ) + pd.to_timedelta(df["HR"], unit="h")
    return df


def picked_3hourly(hourly: pd.DataFrame) -> pd.DataFrame:
    picked = hourly[hourly["HR"].isin(OBSERVED_HOURS)].copy()
    rainfall = rainfall_3hourly_total(hourly)
    picked = picked.drop(columns=["PRECTOTCORR"]).merge(
        rainfall,
        on=["YEAR", "MO", "DY", "HR"],
        how="left",
    )
    return picked[OUTPUT_COLUMNS].sort_values(["YEAR", "MO", "DY", "HR"]).reset_index(drop=True)


def rainfall_3hourly_total(hourly: pd.DataFrame) -> pd.DataFrame:
    working = hourly[["timestamp", "PRECTOTCORR"]].copy()
    working["window_start"] = working["timestamp"].dt.floor("3h")
    rainfall = working.groupby("window_start", as_index=False)["PRECTOTCORR"].sum(min_count=1)
    rainfall.insert(0, "HR", rainfall["window_start"].dt.hour)
    rainfall.insert(0, "DY", rainfall["window_start"].dt.day)
    rainfall.insert(0, "MO", rainfall["window_start"].dt.month)
    rainfall.insert(0, "YEAR", rainfall["window_start"].dt.year)
    return rainfall[["YEAR", "MO", "DY", "HR", "PRECTOTCORR"]]


def average_3hourly(hourly: pd.DataFrame) -> pd.DataFrame:
    working = hourly.copy()
    working["window_start"] = working["timestamp"].dt.floor("3h")
    averaged = working.groupby("window_start", as_index=False)[AVERAGE_COLUMNS].mean()
    rainfall = rainfall_3hourly_total(hourly)
    averaged.insert(0, "HR", averaged["window_start"].dt.hour)
    averaged.insert(0, "DY", averaged["window_start"].dt.day)
    averaged.insert(0, "MO", averaged["window_start"].dt.month)
    averaged.insert(0, "YEAR", averaged["window_start"].dt.year)
    averaged = averaged.merge(rainfall, on=["YEAR", "MO", "DY", "HR"], how="left")
    return averaged[OUTPUT_COLUMNS].sort_values(["YEAR", "MO", "DY", "HR"]).reset_index(drop=True)


def validate_3hourly(df: pd.DataFrame, label: str, station_id: str) -> None:
    if list(df.columns) != OUTPUT_COLUMNS:
        raise ValueError(f"{label} {station_id} has wrong columns: {list(df.columns)}")
    if len(df) != EXPECTED_3H_ROWS:
        raise ValueError(f"{label} {station_id} has {len(df)} rows, expected {EXPECTED_3H_ROWS}")
    hours = sorted(df["HR"].dropna().unique().astype(int).tolist())
    if hours != OBSERVED_HOURS:
        raise ValueError(f"{label} {station_id} has wrong hours: {hours}")
    pd.to_datetime(
        {
            "year": df["YEAR"],
            "month": df["MO"],
            "day": df["DY"],
        },
        errors="raise",
    )


def write_report(report_path: Path, rows: list[dict[str, Any]]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "station_name",
        "station_id",
        "raw_file",
        "picked_file",
        "average_file",
        "hourly_rows",
        "picked_rows",
        "average_rows",
        "status",
        "message",
    ]
    with report_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def process_station(
    station: dict[str, Any],
    raw_dir: Path,
    output_root: Path,
    start: str,
    end: str,
    time_standard: str,
) -> dict[str, Any]:
    station_id = str(station["station_id"])
    station_name = str(station["station_name"])
    raw_path = raw_nasa_path(raw_dir, station_id, start, end, time_standard)
    picked_dir = output_root / "3h_picked"
    average_dir = output_root / "3h_average"
    picked_path = picked_dir / f"{station_id}.csv"
    average_path = average_dir / f"{station_id}.csv"

    row = {
        "station_name": station_name,
        "station_id": station_id,
        "raw_file": str(raw_path.relative_to(PROJECT_ROOT)),
        "picked_file": str(picked_path.relative_to(PROJECT_ROOT)),
        "average_file": str(average_path.relative_to(PROJECT_ROOT)),
        "hourly_rows": "",
        "picked_rows": "",
        "average_rows": "",
        "status": "failed",
        "message": "",
    }

    if not raw_path.exists():
        row["message"] = f"Missing raw NASA file: {raw_path}"
        return row

    hourly = read_hourly_nasa(raw_path)
    picked = picked_3hourly(hourly)
    averaged = average_3hourly(hourly)
    validate_3hourly(picked, "picked", station_id)
    validate_3hourly(averaged, "average", station_id)

    picked_dir.mkdir(parents=True, exist_ok=True)
    average_dir.mkdir(parents=True, exist_ok=True)
    picked.to_csv(picked_path, index=False)
    averaged.to_csv(average_path, index=False)

    row.update(
        {
            "hourly_rows": len(hourly),
            "picked_rows": len(picked),
            "average_rows": len(averaged),
            "status": "processed",
        }
    )
    return row


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create 3-hourly NASA POWER station datasets from hourly raw files."
    )
    parser.add_argument("--stations-json", type=Path, default=DEFAULT_STATIONS_JSON)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--start", default=START)
    parser.add_argument("--end", default=END)
    parser.add_argument("--time-standard", default=TIME_STANDARD)
    parser.add_argument("--station-id", help="Optional single station_id to process.")
    args = parser.parse_args()

    stations = load_stations(args.stations_json)
    if args.station_id:
        stations = [station for station in stations if station["station_id"] == args.station_id]
        if not stations:
            raise ValueError(f"No station found with station_id={args.station_id!r}")

    report_rows = []
    for station in stations:
        try:
            row = process_station(
                station=station,
                raw_dir=args.raw_dir,
                output_root=args.output_root,
                start=args.start,
                end=args.end,
                time_standard=args.time_standard,
            )
        except Exception as exc:
            station_id = str(station.get("station_id", "unknown"))
            print(f"Failed {station_id}: {exc}")
            row = {
                "station_name": station.get("station_name", ""),
                "station_id": station_id,
                "raw_file": "",
                "picked_file": "",
                "average_file": "",
                "hourly_rows": "",
                "picked_rows": "",
                "average_rows": "",
                "status": "failed",
                "message": str(exc),
            }
        report_rows.append(row)
        print(f"{row['status']}: {row['station_id']}")

    write_report(args.report, report_rows)
    processed = sum(1 for row in report_rows if row["status"] == "processed")
    failed = sum(1 for row in report_rows if row["status"] == "failed")
    print(
        f"Done. processed={processed}, failed={failed}, "
        f"picked={args.output_root / '3h_picked'}, "
        f"average={args.output_root / '3h_average'}, report={args.report}"
    )
    if failed:
        raise RuntimeError(f"{failed} station(s) failed. See {args.report}.")


if __name__ == "__main__":
    main()
