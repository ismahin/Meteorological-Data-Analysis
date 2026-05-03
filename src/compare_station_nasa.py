from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import pearsonr


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIONS_FILE = PROJECT_ROOT / "station_metadata.csv"
GROUND_DIR = PROJECT_ROOT / "data" / "raw" / "ground"
NASA_DIR = PROJECT_ROOT / "data" / "raw" / "nasa_power"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
FIGURES_DIR = PROJECT_ROOT / "outputs" / "figures"
TABLES_DIR = PROJECT_ROOT / "outputs" / "tables"

VARIABLE_MAP = {
    "tmean_c": "T2M",
    "tmax_c": "T2M_MAX",
    "tmin_c": "T2M_MIN",
    "rainfall_mm": "PRECTOTCORR",
    "rh_percent": "RH2M",
    "wind_ms": "WS2M",
}


def read_power_csv(path: Path) -> pd.DataFrame:
    lines = path.read_text(encoding="utf-8").splitlines()
    header_end = next(
        (index for index, line in enumerate(lines) if line.strip() == "-END HEADER-"),
        None,
    )
    skiprows = header_end + 1 if header_end is not None else 0
    nasa = pd.read_csv(path, skiprows=skiprows)

    date_parts = ["YEAR", "MO", "DY"]
    missing = [column for column in date_parts if column not in nasa.columns]
    if missing:
        raise ValueError(f"{path.name} is missing NASA date columns: {', '.join(missing)}")

    nasa["date"] = pd.to_datetime(
        {
            "year": nasa["YEAR"].astype(int),
            "month": nasa["MO"].astype(int),
            "day": nasa["DY"].astype(int),
        }
    )
    return nasa.drop(columns=date_parts)


def find_nasa_file(station_id: str) -> Path | None:
    matches = sorted(NASA_DIR.glob(f"{station_id}_*.csv"))
    return matches[-1] if matches else None


def clean_ground(path: Path) -> pd.DataFrame:
    ground = pd.read_csv(path)
    if "date" not in ground.columns:
        raise ValueError(f"{path.name} must contain a date column.")
    ground["date"] = pd.to_datetime(ground["date"])
    return ground


def metrics(ground: pd.Series, nasa: pd.Series) -> dict[str, float]:
    paired = pd.concat([ground, nasa], axis=1).dropna()
    paired.columns = ["ground", "nasa"]
    if paired.empty:
        return {
            "n": 0,
            "bias": math.nan,
            "mae": math.nan,
            "rmse": math.nan,
            "pearson_r": math.nan,
            "percent_bias": math.nan,
        }

    diff = paired["nasa"] - paired["ground"]
    ground_sum = paired["ground"].sum()
    return {
        "n": int(len(paired)),
        "bias": float(diff.mean()),
        "mae": float(diff.abs().mean()),
        "rmse": float(np.sqrt(np.mean(diff**2))),
        "pearson_r": float(pearsonr(paired["ground"], paired["nasa"])[0]) if len(paired) > 1 else math.nan,
        "percent_bias": float(100 * diff.sum() / ground_sum) if ground_sum != 0 else math.nan,
    }


def plot_timeseries(station_id: str, variable: str, matched: pd.DataFrame) -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(matched["date"], matched[f"{variable}_ground"], label="Ground", linewidth=1)
    ax.plot(matched["date"], matched[f"{variable}_nasa"], label="NASA POWER", linewidth=1)
    ax.set_title(f"{station_id} - {variable}")
    ax.set_xlabel("Date")
    ax.set_ylabel(variable)
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / f"{station_id}_{variable}.png", dpi=160)
    plt.close(fig)


def compare_station(station_id: str) -> list[dict[str, float | str]]:
    ground_path = GROUND_DIR / f"{station_id}.csv"
    nasa_path = find_nasa_file(station_id)

    if not ground_path.exists():
        print(f"Missing ground file for {station_id}: {ground_path}")
        return []
    if nasa_path is None:
        print(f"Missing NASA POWER file for {station_id}")
        return []

    ground = clean_ground(ground_path)
    nasa = read_power_csv(nasa_path)
    joined = ground.merge(nasa, on="date", how="inner")

    if joined.empty:
        print(f"No overlapping dates for {station_id}")
        return []

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, float | str]] = []
    output_columns = ["date"]

    for ground_variable, nasa_variable in VARIABLE_MAP.items():
        if ground_variable not in joined.columns or nasa_variable not in joined.columns:
            continue

        joined[f"{ground_variable}_ground"] = joined[ground_variable]
        joined[f"{ground_variable}_nasa"] = joined[nasa_variable]
        output_columns.extend([f"{ground_variable}_ground", f"{ground_variable}_nasa"])

        row = metrics(joined[ground_variable], joined[nasa_variable])
        row.update(
            {
                "station_id": station_id,
                "ground_variable": ground_variable,
                "nasa_parameter": nasa_variable,
            }
        )
        rows.append(row)
        plot_timeseries(station_id, ground_variable, joined)

    if rows:
        joined[output_columns].to_csv(PROCESSED_DIR / f"{station_id}_matched.csv", index=False)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare ground station data with NASA POWER data.")
    parser.add_argument("--stations", type=Path, default=STATIONS_FILE)
    args = parser.parse_args()

    stations = pd.read_csv(args.stations)
    all_rows: list[dict[str, float | str]] = []

    for station_id in stations["station_id"].dropna().astype(str):
        all_rows.extend(compare_station(station_id.strip()))

    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    metrics_table = pd.DataFrame(all_rows)
    metrics_table.to_csv(TABLES_DIR / "comparison_metrics.csv", index=False)
    print(f"Wrote {len(metrics_table)} comparison rows.")


if __name__ == "__main__":
    main()
