from __future__ import annotations

import argparse
import csv
import io
import json
import time
from pathlib import Path
from typing import Any

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATIONS_JSON = PROJECT_ROOT / "data" / "processed" / "bmd_station_coordinates_35.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "nasa_power"
DEFAULT_REPORT = PROJECT_ROOT / "outputs" / "tables" / "nasa_power_download_report.csv"

POWER_HOURLY_POINT_URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"

DEFAULT_START = "20210101"
DEFAULT_END = "20241231"
DEFAULT_PARAMETERS = ["T2M", "RH2M", "PRECTOTCORR", "WS10M"]
DEFAULT_COMMUNITY = "RE"
DEFAULT_TIME_STANDARD = "UTC"
EXPECTED_COLUMNS = ["YEAR", "MO", "DY", "HR", *DEFAULT_PARAMETERS]
EXPECTED_ROWS_2021_2024 = 35064


def parse_parameters(value: str) -> list[str]:
    parameters = [item.strip() for item in value.split(",") if item.strip()]
    if not parameters:
        raise ValueError("At least one NASA POWER parameter is required.")
    return parameters


def load_stations(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    stations = data.get("stations")
    if not isinstance(stations, list):
        raise ValueError(f"{path} must contain a top-level 'stations' list.")

    required = {"station_name", "station_id", "latitude", "longitude"}
    clean_stations = []
    for station in stations:
        missing = required.difference(station)
        if missing:
            raise ValueError(
                f"Station entry is missing required fields: {', '.join(sorted(missing))}"
            )
        clean_stations.append(
            {
                "station_name": str(station["station_name"]),
                "station_id": str(station["station_id"]),
                "latitude": float(station["latitude"]),
                "longitude": float(station["longitude"]),
            }
        )
    return clean_stations


def output_filename(station: dict[str, Any], start: str, end: str, time_standard: str) -> str:
    return f"{station['station_id']}_POWER_Point_Hourly_{start}_{end}_{time_standard}.csv"


def build_request_params(
    station: dict[str, Any],
    start: str,
    end: str,
    parameters: list[str],
    community: str,
    time_standard: str,
) -> dict[str, str | float]:
    return {
        "parameters": ",".join(parameters),
        "community": community,
        "longitude": station["longitude"],
        "latitude": station["latitude"],
        "start": start,
        "end": end,
        "format": "CSV",
        "header": "false",
        "time-standard": time_standard,
    }


def validate_csv(text: str, parameters: list[str]) -> dict[str, Any]:
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise ValueError("NASA POWER returned an empty response.") from exc

    expected_columns = ["YEAR", "MO", "DY", "HR", *parameters]
    if header != expected_columns:
        preview = text[:500].replace("\n", " ")
        raise ValueError(
            f"Unexpected NASA POWER CSV columns: {header}. "
            f"Expected: {expected_columns}. Response preview: {preview}"
        )

    row_count = sum(1 for _ in reader)
    return {
        "columns": ",".join(header),
        "data_rows": row_count,
    }


def request_with_retries(
    session: requests.Session,
    params: dict[str, str | float],
    retries: int,
    timeout: int,
) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = session.get(POWER_HOURLY_POINT_URL, params=params, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt == retries:
                break
            sleep_seconds = min(30, 2**attempt)
            print(f"Request failed on attempt {attempt}; retrying in {sleep_seconds}s...")
            time.sleep(sleep_seconds)
    raise RuntimeError(f"NASA POWER request failed after {retries} attempts.") from last_error


def download_station(
    session: requests.Session,
    station: dict[str, Any],
    output_dir: Path,
    start: str,
    end: str,
    parameters: list[str],
    community: str,
    time_standard: str,
    overwrite: bool,
    retries: int,
    timeout: int,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / output_filename(station, start, end, time_standard)

    report_row: dict[str, Any] = {
        "station_name": station["station_name"],
        "station_id": station["station_id"],
        "latitude": station["latitude"],
        "longitude": station["longitude"],
        "output_file": str(output_path.relative_to(PROJECT_ROOT)),
        "status": "",
        "data_rows": "",
        "columns": "",
        "message": "",
    }

    if output_path.exists() and not overwrite:
        text = output_path.read_text(encoding="utf-8")
        validation = validate_csv(text, parameters)
        report_row.update({"status": "skipped_existing", **validation})
        print(f"Skipping existing file: {output_path.name}")
        return report_row

    params = build_request_params(
        station=station,
        start=start,
        end=end,
        parameters=parameters,
        community=community,
        time_standard=time_standard,
    )
    response = request_with_retries(
        session=session,
        params=params,
        retries=retries,
        timeout=timeout,
    )
    text = response.text
    validation = validate_csv(text, parameters)
    output_path.write_text(text, encoding="utf-8", newline="")
    report_row.update({"status": "downloaded", **validation})
    print(f"Downloaded {station['station_id']}: {output_path.name}")
    return report_row


def write_report(report_path: Path, rows: list[dict[str, Any]]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "station_name",
        "station_id",
        "latitude",
        "longitude",
        "output_file",
        "status",
        "data_rows",
        "columns",
        "message",
    ]
    with report_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download hourly NASA POWER CSV files for the 35 BMD station coordinates."
    )
    parser.add_argument("--stations-json", type=Path, default=DEFAULT_STATIONS_JSON)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--start", default=DEFAULT_START, help="Start date as YYYYMMDD.")
    parser.add_argument("--end", default=DEFAULT_END, help="End date as YYYYMMDD.")
    parser.add_argument(
        "--parameters",
        default=",".join(DEFAULT_PARAMETERS),
        help="Comma-separated NASA POWER parameters.",
    )
    parser.add_argument("--community", default=DEFAULT_COMMUNITY)
    parser.add_argument("--time-standard", choices=["UTC", "LST"], default=DEFAULT_TIME_STANDARD)
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between station requests.")
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--station-id", help="Optional single station_id to download.")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    parameters = parse_parameters(args.parameters)
    stations = load_stations(args.stations_json)
    if args.station_id:
        stations = [station for station in stations if station["station_id"] == args.station_id]
        if not stations:
            raise ValueError(f"No station found with station_id={args.station_id!r}")

    print(
        f"Downloading NASA POWER hourly data for {len(stations)} station(s): "
        f"{args.start}-{args.end}, community={args.community}, "
        f"time-standard={args.time_standard}, parameters={','.join(parameters)}"
    )

    report_rows = []
    with requests.Session() as session:
        for index, station in enumerate(stations, start=1):
            try:
                report_rows.append(
                    download_station(
                        session=session,
                        station=station,
                        output_dir=args.output_dir,
                        start=args.start,
                        end=args.end,
                        parameters=parameters,
                        community=args.community,
                        time_standard=args.time_standard,
                        overwrite=args.overwrite,
                        retries=args.retries,
                        timeout=args.timeout,
                    )
                )
            except Exception as exc:
                print(f"Failed {station['station_id']}: {exc}")
                report_rows.append(
                    {
                        "station_name": station["station_name"],
                        "station_id": station["station_id"],
                        "latitude": station["latitude"],
                        "longitude": station["longitude"],
                        "output_file": str(
                            (
                                args.output_dir
                                / output_filename(station, args.start, args.end, args.time_standard)
                            ).relative_to(PROJECT_ROOT)
                        ),
                        "status": "failed",
                        "data_rows": "",
                        "columns": "",
                        "message": str(exc),
                    }
                )
            if index < len(stations):
                time.sleep(args.delay)

    write_report(args.report, report_rows)
    downloaded = sum(1 for row in report_rows if row["status"] == "downloaded")
    skipped = sum(1 for row in report_rows if row["status"] == "skipped_existing")
    failed = sum(1 for row in report_rows if row["status"] == "failed")
    print(
        f"Done. downloaded={downloaded}, skipped_existing={skipped}, "
        f"failed={failed}, report={args.report}"
    )
    if args.start == DEFAULT_START and args.end == DEFAULT_END:
        wrong_rows = [
            row
            for row in report_rows
            if row["status"] != "failed" and int(row["data_rows"]) != EXPECTED_ROWS_2021_2024
        ]
        if wrong_rows:
            raise RuntimeError(
                "Some files did not contain the expected "
                f"{EXPECTED_ROWS_2021_2024} hourly rows."
            )


if __name__ == "__main__":
    main()
