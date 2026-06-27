from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def env_path(name: str, default: Path) -> Path:
    value = os.getenv(name)
    return Path(value).expanduser().resolve() if value else default


DEFAULT_STATIONS_JSON = env_path(
    "BMD_STATIONS_JSON",
    PROJECT_ROOT / "data" / "processed" / "bmd_station_coordinates_35.json",
)
DEFAULT_BMD_DIR = env_path(
    "BMD_TIMESERIES_DIR",
    PROJECT_ROOT / "data" / "processed" / "ogimet_synop" / "by_station",
)
DEFAULT_NASA_DIR = env_path(
    "NASA_STATION_TIMESERIES_DIR",
    PROJECT_ROOT / "data" / "processed" / "nasa_station_data" / "3h_picked",
)
DEFAULT_MODEL_DIR = env_path("MODEL_DIR", PROJECT_ROOT / "models" / "bias_correction")

POWER_HOURLY_POINT_URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"
VARIABLES = ["T2M", "RH2M", "PRECTOTCORR", "WS10M"]
OBSERVED_HOURS = [0, 3, 6, 9, 12, 15, 18, 21]
START_DATE = pd.Timestamp("2021-01-01 00:00:00")
TRAINING_END_DATE = pd.Timestamp("2024-12-31 21:00:00")
K_NEAREST = 5
RAIN_THRESHOLD_MM = 0.1
BANGLADESH_BOUNDS = {
    "lat_min": 20.5,
    "lat_max": 26.8,
    "lon_min": 88.0,
    "lon_max": 92.8,
}


@dataclass(frozen=True)
class Station:
    station_id: str
    station_name: str
    latitude: float
    longitude: float


def load_stations(path: Path = DEFAULT_STATIONS_JSON) -> list[Station]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        Station(
            station_id=str(item["station_id"]),
            station_name=str(item["station_name"]),
            latitude=float(item["latitude"]),
            longitude=float(item["longitude"]),
        )
        for item in data["stations"]
    ]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius_km * math.asin(math.sqrt(a))


def season_code(month: int) -> int:
    if month in {12, 1, 2}:
        return 0
    if month in {3, 4, 5}:
        return 1
    if month in {6, 7, 8, 9}:
        return 2
    return 3


def parse_timestamp_utc(value: str) -> pd.Timestamp:
    text = value.strip()
    if re.search(r"([+-]\d{2}:?\d{2})$", text) and not re.search(r"(\+00:?00)$", text):
        raise ValueError("timestamp_utc must be UTC. Use a Z suffix, +00:00 offset, or no offset for UTC input.")
    text = text.replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    ts = pd.Timestamp(dt)
    if ts < START_DATE:
        raise ValueError("timestamp_utc must be on or after 2021-01-01T00:00:00Z.")
    if ts.minute or ts.second or ts.microsecond or ts.hour not in OBSERVED_HOURS:
        raise ValueError("timestamp_utc must be on a 3-hour UTC step: 00,03,06,09,12,15,18,21.")
    return ts


def latest_3hour_utc(now: datetime | None = None) -> pd.Timestamp:
    current = now or datetime.now(timezone.utc)
    current = current.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0, tzinfo=None)
    return pd.Timestamp(current.replace(hour=(current.hour // 3) * 3))


def validate_bangladesh_coordinate(latitude: float, longitude: float) -> None:
    if not (BANGLADESH_BOUNDS["lat_min"] <= latitude <= BANGLADESH_BOUNDS["lat_max"]):
        raise ValueError("latitude is outside the supported Bangladesh bounding box.")
    if not (BANGLADESH_BOUNDS["lon_min"] <= longitude <= BANGLADESH_BOUNDS["lon_max"]):
        raise ValueError("longitude is outside the supported Bangladesh bounding box.")


def timestamp_key(ts: pd.Timestamp) -> tuple[int, int, int, int]:
    return int(ts.year), int(ts.month), int(ts.day), int(ts.hour)


def load_station_timeseries(
    stations: list[Station],
    bmd_dir: Path = DEFAULT_BMD_DIR,
    nasa_dir: Path = DEFAULT_NASA_DIR,
) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for station in stations:
        bmd = pd.read_csv(bmd_dir / f"{station.station_id}.csv")
        nasa = pd.read_csv(nasa_dir / f"{station.station_id}.csv")
        merged = bmd.merge(
            nasa,
            on=["YEAR", "MO", "DY", "HR"],
            suffixes=("_bmd", "_nasa"),
            validate="one_to_one",
        )
        merged["timestamp"] = pd.to_datetime(
            {"year": merged["YEAR"], "month": merged["MO"], "day": merged["DY"]}
        ) + pd.to_timedelta(merged["HR"], unit="h")
        frames[station.station_id] = merged
    return frames


def station_distance_table(stations: list[Station]) -> pd.DataFrame:
    rows = []
    for source in stations:
        for target in stations:
            if source.station_id == target.station_id:
                continue
            rows.append(
                {
                    "source_station_id": source.station_id,
                    "target_station_id": target.station_id,
                    "distance_km": haversine_km(
                        source.latitude,
                        source.longitude,
                        target.latitude,
                        target.longitude,
                    ),
                }
            )
    return pd.DataFrame(rows)


def nearest_stations(
    latitude: float,
    longitude: float,
    stations: list[Station],
    *,
    exclude_station_id: str | None = None,
    k: int = K_NEAREST,
) -> list[tuple[Station, float]]:
    candidates = []
    for station in stations:
        if station.station_id == exclude_station_id:
            continue
        candidates.append(
            (
                station,
                haversine_km(latitude, longitude, station.latitude, station.longitude),
            )
        )
    return sorted(candidates, key=lambda item: item[1])[:k]


def inverse_distance_residual(
    anchor_values: list[float],
    anchor_nasa_values: list[float],
    distances: list[float],
    decay_km: float,
) -> float:
    for value, nasa_value, distance in zip(anchor_values, anchor_nasa_values, distances):
        if pd.notna(value) and pd.notna(nasa_value) and pd.notna(distance) and float(distance) <= 1e-6:
            return float(value - nasa_value)
    weights = []
    residuals = []
    for value, nasa_value, distance in zip(anchor_values, anchor_nasa_values, distances):
        if pd.isna(value) or pd.isna(nasa_value):
            continue
        weights.append(math.exp(-max(distance, 0.01) / decay_km) / max(distance, 0.01))
        residuals.append(value - nasa_value)
    if not weights:
        return 0.0
    w = np.asarray(weights)
    r = np.asarray(residuals)
    return float(np.average(r, weights=w))


def inverse_distance_average(values: list[float], distances: list[float], decay_km: float) -> float:
    for value, distance in zip(values, distances):
        if pd.notna(value) and pd.notna(distance) and float(distance) <= 1e-6:
            return float(value)
    weights = []
    clean_values = []
    for value, distance in zip(values, distances):
        if pd.isna(value) or pd.isna(distance):
            continue
        weights.append(math.exp(-max(distance, 0.01) / decay_km) / max(distance, 0.01))
        clean_values.append(value)
    if not weights:
        return math.nan
    return float(np.average(np.asarray(clean_values), weights=np.asarray(weights)))


def build_feature_row(
    *,
    latitude: float,
    longitude: float,
    timestamp: pd.Timestamp,
    target_nasa: dict[str, float],
    anchors: list[tuple[Station, float, pd.Series]],
    variable: str,
    decay_km: float,
) -> dict[str, float]:
    month = int(timestamp.month)
    hour = int(timestamp.hour)
    anchor_bmd = [float(row.get(f"{variable}_bmd", np.nan)) for _, _, row in anchors]
    anchor_nasa = [float(row.get(f"{variable}_nasa", np.nan)) for _, _, row in anchors]
    distances = [float(distance) for _, distance, _ in anchors]
    while len(anchor_bmd) < K_NEAREST:
        anchor_bmd.append(np.nan)
        anchor_nasa.append(np.nan)
        distances.append(np.nan)

    nasa_value = float(target_nasa[variable])
    idw_residual = inverse_distance_residual(anchor_bmd, anchor_nasa, distances, decay_km)
    anchor_idw_bmd = inverse_distance_average(anchor_bmd, distances, decay_km)
    anchor_idw_nasa = inverse_distance_average(anchor_nasa, distances, decay_km)
    row = {
        "nasa_value": nasa_value,
        "anchor_idw_bmd": anchor_idw_bmd,
        "anchor_idw_nasa": anchor_idw_nasa,
        "nasa_minus_anchor_idw_nasa": nasa_value - anchor_idw_nasa if not pd.isna(anchor_idw_nasa) else np.nan,
        "latitude": float(latitude),
        "longitude": float(longitude),
        "month": float(month),
        "hour": float(hour),
        "season": float(season_code(month)),
        "sin_month": math.sin(2 * math.pi * month / 12),
        "cos_month": math.cos(2 * math.pi * month / 12),
        "sin_hour": math.sin(2 * math.pi * hour / 24),
        "cos_hour": math.cos(2 * math.pi * hour / 24),
        "idw_residual": idw_residual,
        "idw_corrected": nasa_value + idw_residual,
    }
    for index in range(K_NEAREST):
        bmd_value = anchor_bmd[index]
        nasa_anchor = anchor_nasa[index]
        distance = distances[index]
        residual = bmd_value - nasa_anchor if not pd.isna(bmd_value) and not pd.isna(nasa_anchor) else np.nan
        row[f"anchor{index + 1}_bmd"] = bmd_value
        row[f"anchor{index + 1}_nasa"] = nasa_anchor
        row[f"anchor{index + 1}_residual"] = residual
        row[f"anchor{index + 1}_distance_km"] = distance
    return row


def download_nasa_point(
    latitude: float,
    longitude: float,
    timestamp: pd.Timestamp,
    *,
    parameters: list[str] | None = None,
    timeout: int = 120,
) -> dict[str, float]:
    parameters = parameters or VARIABLES
    date = timestamp.strftime("%Y%m%d")
    params = {
        "parameters": ",".join(parameters),
        "community": "RE",
        "longitude": longitude,
        "latitude": latitude,
        "start": date,
        "end": date,
        "format": "JSON",
        "time-standard": "UTC",
    }
    response = requests.get(POWER_HOURLY_POINT_URL, params=params, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    hour_key = timestamp.strftime("%Y%m%d%H")
    values = {}
    for variable in parameters:
        series = data["properties"]["parameter"][variable]
        values[variable] = float(series[hour_key])
    return values


def complete_nasa_values(values: dict[str, float], parameters: list[str]) -> bool:
    for parameter in parameters:
        value = values.get(parameter)
        if value is None or pd.isna(value) or float(value) <= -900:
            return False
    return True


def download_latest_valid_nasa_point(
    latitude: float,
    longitude: float,
    timestamp: pd.Timestamp,
    *,
    parameters: list[str] | None = None,
    max_lookback_days: int = 45,
    timeout: int = 120,
) -> tuple[dict[str, float], pd.Timestamp]:
    parameters = parameters or VARIABLES
    cursor = min(timestamp, latest_3hour_utc())
    attempts = max_lookback_days * 8 + 1
    for _ in range(attempts):
        try:
            values = download_nasa_point(
                latitude,
                longitude,
                cursor,
                parameters=parameters,
                timeout=timeout,
            )
            if complete_nasa_values(values, parameters):
                return values, cursor
        except Exception:
            pass
        cursor = cursor - pd.Timedelta(hours=3)
        if cursor < START_DATE:
            break
    raise ValueError(f"No complete NASA POWER data found within {max_lookback_days} days before {timestamp.isoformat()}Z.")


def climatology_station_row(frame: pd.DataFrame, timestamp: pd.Timestamp) -> pd.Series:
    month = int(timestamp.month)
    hour = int(timestamp.hour)
    subset = frame[(frame["MO"] == month) & (frame["HR"] == hour)]
    if subset.empty:
        subset = frame
    values: dict[str, float] = {
        "YEAR": int(timestamp.year),
        "MO": month,
        "DY": int(timestamp.day),
        "HR": hour,
        "timestamp": timestamp,
    }
    for variable in VARIABLES:
        for source in ["bmd", "nasa"]:
            column = f"{variable}_{source}"
            series = subset[column].dropna()
            if series.empty:
                series = frame[column].dropna()
            values[column] = float(series.median()) if not series.empty else 0.0
    return pd.Series(values)


def no_nan_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(numeric) or math.isinf(numeric) or numeric <= -900 else numeric


def local_station_nasa_value(
    frames: dict[str, pd.DataFrame],
    station_id: str,
    timestamp: pd.Timestamp,
    variable: str,
) -> float:
    year, month, day, hour = timestamp_key(timestamp)
    df = frames[station_id]
    row = df[
        (df["YEAR"] == year)
        & (df["MO"] == month)
        & (df["DY"] == day)
        & (df["HR"] == hour)
    ]
    if row.empty:
        raise ValueError(f"No station data for {station_id} at {timestamp.isoformat()}.")
    return float(row.iloc[0][f"{variable}_nasa"])


def load_model_bundle(model_dir: Path = DEFAULT_MODEL_DIR) -> dict[str, Any]:
    bundle_path = model_dir / "model_bundle.joblib"
    if not bundle_path.exists():
        raise FileNotFoundError(f"Missing model artifact: {bundle_path}. Run train_bias_correction_model.py first.")
    return joblib.load(bundle_path)


def uncertainty_for(
    validation_residuals: pd.DataFrame,
    variable: str,
    season: int,
    distance_km: float,
) -> dict[str, float]:
    if validation_residuals.empty:
        return {"p05": math.nan, "p50": math.nan, "p95": math.nan}
    bins = [0, 25, 50, 100, 150, 250, np.inf]
    labels = ["0-25", "25-50", "50-100", "100-150", "150-250", "250+"]
    bucket = labels[int(np.digitize([distance_km], bins, right=False)[0]) - 1]
    subset = validation_residuals[
        (validation_residuals["variable"] == variable)
        & (validation_residuals["season"] == season)
        & (validation_residuals["distance_bucket"] == bucket)
    ]
    if subset.empty:
        subset = validation_residuals[validation_residuals["variable"] == variable]
    values = subset["residual"].dropna()
    if values.empty:
        return {"p05": math.nan, "p50": math.nan, "p95": math.nan}
    return {
        "p05": float(values.quantile(0.05)),
        "p50": float(values.quantile(0.50)),
        "p95": float(values.quantile(0.95)),
    }
