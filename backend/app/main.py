from __future__ import annotations

import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .bias_correction_core import (
    DEFAULT_MODEL_DIR,
    K_NEAREST,
    RAIN_THRESHOLD_MM,
    TRAINING_END_DATE,
    VARIABLES,
    Station,
    build_feature_row,
    climatology_station_row,
    download_latest_valid_nasa_point,
    download_nasa_point,
    load_model_bundle,
    load_station_timeseries,
    load_stations,
    nearest_stations,
    no_nan_float,
    parse_timestamp_utc,
    season_code,
    uncertainty_for,
    validate_bangladesh_coordinate,
)


class CorrectionRequest(BaseModel):
    latitude: float = Field(..., ge=20.5, le=26.8)
    longitude: float = Field(..., ge=88.0, le=92.8)
    timestamp_utc: str
    variables: list[str] = Field(default_factory=lambda: VARIABLES.copy())



def cors_origins() -> list[str]:
    raw = os.getenv("BACKEND_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(title="Bangladesh NASA-BMD Bias Correction API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def runtime() -> dict[str, Any]:
    stations = load_stations()
    frames = load_station_timeseries(stations)
    bundle = load_model_bundle(DEFAULT_MODEL_DIR)
    return {"stations": stations, "frames": frames, "bundle": bundle}


def row_at_timestamp(frame: pd.DataFrame, timestamp: pd.Timestamp) -> pd.Series:
    row = frame[frame["timestamp"] == timestamp]
    if row.empty:
        raise ValueError(f"No BMD/NASA station row for {timestamp.isoformat()}.")
    return row.iloc[0]


def clean_number(value: Any, default: float = 0.0) -> float:
    return no_nan_float(value, default=default)


def clamp_variable(variable: str, value: float) -> float:
    value = clean_number(value)
    if variable == "RH2M":
        return max(0.0, min(100.0, value))
    if variable in {"PRECTOTCORR", "WS10M"}:
        return max(0.0, value)
    return value


def station_payload(station: Station, distance_km: float, row: pd.Series, variables: list[str]) -> dict[str, Any]:
    return {
        "station_id": station.station_id,
        "station_name": station.station_name,
        "latitude": station.latitude,
        "longitude": station.longitude,
        "distance_km": distance_km,
        "observations": {
            variable: clean_number(row.get(f"{variable}_bmd"))
            for variable in variables
        },
        "nasa_at_station": {
            variable: clean_number(row.get(f"{variable}_nasa"))
            for variable in variables
        },
    }


def predict_variable(
    *,
    bundle: dict[str, Any],
    feature: dict[str, float],
    variable: str,
) -> tuple[float, float | None]:
    model_name = bundle["selected_models"][variable]
    frame = pd.DataFrame([feature], columns=bundle["feature_columns"])
    if model_name == "raw_nasa":
        return float(feature["nasa_value"]), None
    if model_name == "anchor_idw_bmd":
        return float(feature["anchor_idw_bmd"]), None
    if model_name == "idw_residual":
        return float(feature["idw_corrected"]), None
    if model_name == "global_month_hour_bias":
        artifact = bundle["models"][variable]
        key = f"{int(feature['month'])}-{int(feature['hour'])}"
        offset = artifact["offsets"].get(key, artifact["fallback"])
        return float(feature["nasa_value"] + offset), None
    if model_name == "linear_stack":
        artifact = bundle["models"][variable]
        global_artifact = artifact["global_bias"]
        key = f"{int(feature['month'])}-{int(feature['hour'])}"
        offset = global_artifact["offsets"].get(key, global_artifact["fallback"])
        stack_row = {
            "nasa_value": feature["nasa_value"],
            "anchor_idw_bmd": feature["anchor_idw_bmd"],
            "idw_corrected": feature["idw_corrected"],
            "global_month_hour_bias": feature["nasa_value"] + offset,
            "month": feature["month"],
            "hour": feature["hour"],
            "season": feature["season"],
            "nearest_distance_km": feature["anchor1_distance_km"],
        }
        for column, value in artifact["medians"].items():
            if pd.isna(stack_row.get(column)):
                stack_row[column] = value
        frame = pd.DataFrame([stack_row], columns=artifact["columns"])
        value = float(artifact["model"].predict(frame)[0])
        if variable == "PRECTOTCORR":
            value = max(0.0, value)
        return value, None
    artifact = bundle["models"][variable]
    if model_name == "ml_two_stage":
        classifier, regressor = artifact
        wet_probability = float(classifier.predict_proba(frame)[0, 1])
        amount = float(np.expm1(regressor.predict(frame)[0]))
        return (amount if wet_probability >= 0.5 else 0.0), wet_probability
    return float(artifact.predict(frame)[0]), None


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "Bangladesh NASA-BMD Bias Correction API",
        "status": "ok",
        "docs": "/docs",
    }


@app.get("/api/stations")
def stations() -> dict[str, Any]:
    data = runtime()
    return {
        "stations": [
            {
                "station_id": station.station_id,
                "station_name": station.station_name,
                "latitude": station.latitude,
                "longitude": station.longitude,
            }
            for station in data["stations"]
        ]
    }


@app.post("/api/correct")
def correct(request: CorrectionRequest) -> dict[str, Any]:
    try:
        validate_bangladesh_coordinate(request.latitude, request.longitude)
        requested_timestamp = parse_timestamp_utc(request.timestamp_utc)
        variables = [variable for variable in request.variables if variable in VARIABLES]
        if not variables:
            raise ValueError(f"At least one supported variable is required: {', '.join(VARIABLES)}")

        data = runtime()
        stations_list: list[Station] = data["stations"]
        frames: dict[str, pd.DataFrame] = data["frames"]
        bundle: dict[str, Any] = data["bundle"]
        nasa_values, resolved_timestamp = download_latest_valid_nasa_point(
            request.latitude,
            request.longitude,
            requested_timestamp,
            parameters=variables,
        )
        operational_mode = resolved_timestamp > TRAINING_END_DATE

        nearest = nearest_stations(
            request.latitude,
            request.longitude,
            stations_list,
            k=K_NEAREST,
        )
        anchors = []
        anchor_payloads = []
        for station, distance in nearest:
            if operational_mode:
                row = climatology_station_row(frames[station.station_id], resolved_timestamp)
                try:
                    station_nasa = download_nasa_point(
                        station.latitude,
                        station.longitude,
                        resolved_timestamp,
                        parameters=variables,
                        timeout=60,
                    )
                    for variable in variables:
                        if station_nasa.get(variable) is not None and float(station_nasa.get(variable)) > -900:
                            row[f"{variable}_nasa"] = clean_number(station_nasa.get(variable), row.get(f"{variable}_nasa", 0.0))
                except Exception:
                    pass
            else:
                row = row_at_timestamp(frames[station.station_id], resolved_timestamp)
            anchors.append((station, distance, row))
            anchor_payloads.append(station_payload(station, distance, row, variables))

        estimates = {}
        season = season_code(int(resolved_timestamp.month))
        for variable in variables:
            feature = build_feature_row(
                latitude=request.latitude,
                longitude=request.longitude,
                timestamp=resolved_timestamp,
                target_nasa={variable: clean_number(nasa_values[variable])},
                anchors=anchors,
                variable=variable,
                decay_km=float(bundle["selected_decays_km"][variable]),
            )
            corrected, wet_probability = predict_variable(bundle=bundle, feature=feature, variable=variable)
            corrected = clamp_variable(variable, corrected)
            nearest_value = anchors[0][2].get(f"{variable}_bmd")
            uncertainty = uncertainty_for(
                bundle["validation_residuals"],
                variable,
                season,
                float(anchors[0][1]),
            )
            estimates[variable] = {
                "raw_nasa": clamp_variable(variable, nasa_values[variable]),
                "nearest_bmd_station_value": clamp_variable(variable, nearest_value),
                "corrected": corrected,
                "uncertainty_residual_p05": clean_number(uncertainty["p05"]),
                "uncertainty_residual_p50": clean_number(uncertainty["p50"]),
                "uncertainty_residual_p95": clean_number(uncertainty["p95"]),
                "selected_model": bundle["selected_models"][variable],
                "distance_decay_km": bundle["selected_decays_km"][variable],
            }
            if variable == "PRECTOTCORR":
                estimates[variable]["wet_probability"] = clean_number(wet_probability)
                estimates[variable]["rain_threshold_mm"] = RAIN_THRESHOLD_MM

        return {
            "requested_timestamp_utc": requested_timestamp.isoformat() + "Z",
            "resolved_timestamp_utc": resolved_timestamp.isoformat() + "Z",
            "timestamp_utc": resolved_timestamp.isoformat() + "Z",
            "nasa_data_lag_hours": clean_number((requested_timestamp - resolved_timestamp) / pd.Timedelta(hours=1)),
            "mode": "operational_climatology_anchors" if operational_mode else "historical_observed_anchors",
            "location": {"latitude": request.latitude, "longitude": request.longitude},
            "nearest_station": anchor_payloads[0],
            "anchors": anchor_payloads,
            "estimates": estimates,
            "model": {
                "version": bundle["version"],
                "holdout_stations": bundle["holdout_stations"],
            },
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
