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
    START_DATE,
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
from .nasa_power import NasaPowerClient, NasaPowerError, utc_now_3hour
from .operational_forecast import (
    MAX_FORECAST_HOURS,
    OperationalForecastModel,
    build_forecast_features,
    clamp_value,
)


class CorrectionRequest(BaseModel):
    latitude: float = Field(..., ge=20.5, le=26.8)
    longitude: float = Field(..., ge=88.0, le=92.8)
    timestamp_utc: str
    variables: list[str] = Field(default_factory=lambda: VARIABLES.copy())


OPERATIONAL_MODEL_PATH = Path(
    os.getenv(
        "OPERATIONAL_MODEL_PATH",
        str(Path(__file__).resolve().parents[1] / "models" / "operational_forecast" / "model_bundle.joblib"),
    )
)
NASA_HISTORY_DAYS = int(os.getenv("NASA_HISTORY_DAYS", "90"))
nasa_client = NasaPowerClient(
    cache_ttl_seconds=int(os.getenv("NASA_CACHE_TTL_SECONDS", "3600")),
    stale_ttl_seconds=int(os.getenv("NASA_STALE_CACHE_SECONDS", "86400")),
    timeout_seconds=int(os.getenv("NASA_TIMEOUT_SECONDS", "45")),
    retries=int(os.getenv("NASA_RETRIES", "2")),
)



def cors_origins() -> list[str]:
    raw = os.getenv("BACKEND_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(title="Bangladesh NASA-BMD Operational Forecast API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def station_runtime() -> list[Station]:
    return load_stations()


@lru_cache(maxsize=1)
def runtime() -> dict[str, Any]:
    stations = station_runtime()
    frames = load_station_timeseries(stations)
    bundle = load_model_bundle(DEFAULT_MODEL_DIR)
    return {"stations": stations, "frames": frames, "bundle": bundle}


@lru_cache(maxsize=1)
def operational_model() -> OperationalForecastModel:
    return OperationalForecastModel.load(OPERATIONAL_MODEL_PATH)


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


def climatology_anchors_for_correction(
    *,
    data: dict[str, Any],
    latitude: float,
    longitude: float,
    timestamp: pd.Timestamp,
) -> list[tuple[Station, float, pd.Series]]:
    nearest = nearest_stations(latitude, longitude, data["stations"], k=K_NEAREST)
    return [
        (station, distance, climatology_station_row(data["frames"][station.station_id], timestamp))
        for station, distance in nearest
    ]


def operational_anchors_for_correction(
    *,
    base_anchors: list[tuple[Station, float, pd.Series]],
    history: pd.DataFrame,
    origin: pd.Timestamp,
    target: pd.Timestamp,
    variable: str,
    model: OperationalForecastModel,
) -> list[tuple[Station, float, pd.Series]]:
    anchors: list[tuple[Station, float, pd.Series]] = []
    for station, distance, base_row in base_anchors:
        row = base_row.copy()
        features = build_forecast_features(
            history.loc[:origin],
            origin=origin,
            target=target,
            latitude=station.latitude,
            longitude=station.longitude,
        )
        prediction = model.predict(variable, features)
        if prediction.status == "available":
            row[f"{variable}_bmd"] = prediction.bmd_equivalent
            row[f"{variable}_nasa"] = prediction.raw_forecast
        anchors.append((station, distance, row))
    return anchors


def previous_model_correction(
    *,
    data: dict[str, Any],
    anchors: list[tuple[Station, float, pd.Series]],
    latitude: float,
    longitude: float,
    timestamp: pd.Timestamp,
    variable: str,
    nasa_value: float,
) -> dict[str, Any]:
    bundle = data["bundle"]
    feature = build_feature_row(
        latitude=latitude,
        longitude=longitude,
        timestamp=timestamp,
        target_nasa={variable: clamp_variable(variable, nasa_value)},
        anchors=anchors,
        variable=variable,
        decay_km=float(bundle["selected_decays_km"][variable]),
    )
    corrected, wet_probability = predict_variable(bundle=bundle, feature=feature, variable=variable)
    corrected = clamp_variable(variable, corrected)
    uncertainty = uncertainty_for(
        bundle["validation_residuals"],
        variable,
        season_code(int(timestamp.month)),
        float(anchors[0][1]),
    )
    lower = clamp_variable(variable, corrected + clean_number(uncertainty["p05"]))
    upper = clamp_variable(variable, corrected + clean_number(uncertainty["p95"]))
    return {
        "corrected": corrected,
        "p05": min(lower, upper),
        "p50": corrected,
        "p95": max(lower, upper),
        "wet_probability": wet_probability,
        "model_version": str(bundle["version"]),
        "method": str(bundle["selected_models"][variable]),
        "anchor_station_id": anchors[0][0].station_id,
        "anchor_station_name": anchors[0][0].station_name,
        "anchor_distance_km": float(anchors[0][1]),
        "anchor_value_source": "operational_model_forecast",
    }


def apply_previous_correction(payload: dict[str, Any], correction: dict[str, Any]) -> None:
    payload["corrected_nasa"] = correction["corrected"]
    payload["p05"] = correction["p05"]
    payload["p50"] = correction["p50"]
    payload["p95"] = correction["p95"]
    payload["correction_model_version"] = correction["model_version"]
    payload["correction_method"] = correction["method"]
    payload["correction_anchor_station_id"] = correction["anchor_station_id"]
    payload["correction_anchor_station_name"] = correction["anchor_station_name"]
    payload["correction_anchor_distance_km"] = correction["anchor_distance_km"]
    payload["correction_anchor_value_source"] = correction["anchor_value_source"]
    if correction["wet_probability"] is not None:
        payload["wet_probability"] = correction["wet_probability"]


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
    data = station_runtime()
    return {
        "stations": [
            {
                "station_id": station.station_id,
                "station_name": station.station_name,
                "latitude": station.latitude,
                "longitude": station.longitude,
            }
            for station in data
        ]
    }


@app.post("/api/correct", deprecated=True)
def correct(request: CorrectionRequest) -> dict[str, Any]:
    try:
        validate_bangladesh_coordinate(request.latitude, request.longitude)
        requested_timestamp = parse_timestamp_utc(request.timestamp_utc)
        if requested_timestamp > TRAINING_END_DATE:
            raise HTTPException(
                status_code=409,
                detail="Post-2024 requests require /api/v2/estimate; historical BMD climatology is not a live observation.",
            )
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
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def iso_utc(timestamp: pd.Timestamp) -> str:
    return pd.Timestamp(timestamp).strftime("%Y-%m-%dT%H:%M:%SZ")


def operational_payload(
    *,
    variable: str,
    prediction: Any,
    timestamp: pd.Timestamp,
    source: str,
    classification: str,
    raw_override: float | None = None,
) -> dict[str, Any]:
    nasa_value = (
        clamp_value(variable, raw_override)
        if raw_override is not None
        else prediction.raw_forecast
    )
    payload = {
        "status": prediction.status,
        "source": source,
        "classification": classification,
        "timestamp_utc": iso_utc(timestamp),
        "raw_forecast": nasa_value,
        "bmd_equivalent": prediction.bmd_equivalent,
        "nasa_raw": None,
        "bmd_raw": None,
        "nasa_forecast": None,
        "bmd_forecast": None,
        "bmd_actual": None,
        "bmd_estimate": None,
        "bmd_data_kind": "model_forecast" if classification == "provisional_forecast" else "model_estimate",
        "bmd_observation_available": False,
        "bmd_source": "NASA_BMD_operational_model",
        "bmd_data_timestamp_utc": iso_utc(timestamp),
        "corrected_nasa": None,
        "correction_model_version": None,
        "correction_method": None,
        "correction_anchor_station_id": None,
        "correction_anchor_station_name": None,
        "correction_anchor_distance_km": None,
        "correction_anchor_value_source": None,
        "p05": prediction.p05,
        "p50": prediction.p50,
        "p95": prediction.p95,
        "wet_probability": prediction.wet_probability,
        "model_version": prediction.model_version,
        "reason": prediction.reason,
    }
    if classification == "provisional_forecast":
        payload["nasa_forecast"] = nasa_value
        payload["bmd_forecast"] = prediction.bmd_equivalent
    else:
        payload["nasa_raw"] = nasa_value
        payload["bmd_estimate"] = prediction.bmd_equivalent
    return payload


def historical_v2_payload(request: CorrectionRequest) -> dict[str, Any]:
    result = correct(request)
    estimates: dict[str, Any] = {}
    for variable, estimate in result["estimates"].items():
        corrected = clamp_value(variable, estimate["corrected"])
        lower = clamp_value(variable, corrected + estimate["uncertainty_residual_p05"])
        upper = clamp_value(variable, corrected + estimate["uncertainty_residual_p95"])
        requested = {
            "status": "available",
            "source": "BMD_NASA_historical",
            "classification": "historical_correction",
            "timestamp_utc": result["resolved_timestamp_utc"],
            "raw_forecast": estimate["raw_nasa"],
            "bmd_equivalent": corrected,
            "nasa_raw": estimate["raw_nasa"],
            "bmd_raw": estimate["nearest_bmd_station_value"],
            "nasa_forecast": None,
            "bmd_forecast": None,
            "bmd_actual": estimate["nearest_bmd_station_value"],
            "bmd_estimate": corrected,
            "bmd_data_kind": "actual_observation",
            "bmd_observation_available": True,
            "bmd_source": "BMD_historical_archive",
            "bmd_data_timestamp_utc": result["resolved_timestamp_utc"],
            "corrected_nasa": corrected,
            "correction_model_version": result["model"]["version"],
            "correction_method": estimate.get("selected_model", "legacy_bias_correction"),
            "correction_anchor_station_id": result["nearest_station"]["station_id"],
            "correction_anchor_station_name": result["nearest_station"]["station_name"],
            "correction_anchor_distance_km": result["nearest_station"]["distance_km"],
            "correction_anchor_value_source": "historical_observation",
            "p05": min(lower, upper),
            "p50": corrected,
            "p95": max(lower, upper),
            "wet_probability": estimate.get("wet_probability"),
            "model_version": result["model"]["version"],
            "reason": None,
        }
        estimates[variable] = {"requested": requested, "latest_nasa": requested.copy()}
    return {
        "status": "complete",
        "requested_timestamp_utc": result["requested_timestamp_utc"],
        "latest_nasa_timestamp_utc": result["resolved_timestamp_utc"],
        "nasa_data_lag_hours": result["nasa_data_lag_hours"],
        "forecast_horizon_hours": 0.0,
        "mode": "historical_correction",
        "location": result["location"],
        "nearest_station": {
            key: result["nearest_station"][key]
            for key in ("station_id", "station_name", "latitude", "longitude", "distance_km")
        },
        "estimates": estimates,
        "attribution": ["Bangladesh Meteorological Department (BMD)", "NASA POWER"],
        "data_warning": None,
        "bmd_live_enabled": False,
        "bmd_data_status": {
            "kind": "actual_observation",
            "observation_available": True,
            "source": "BMD_historical_archive",
            "archive_start_utc": iso_utc(START_DATE),
            "archive_end_utc": iso_utc(TRAINING_END_DATE),
            "reason": None,
        },
    }


@app.post("/api/v2/estimate")
def estimate_v2(request: CorrectionRequest) -> dict[str, Any]:
    validate_bangladesh_coordinate(request.latitude, request.longitude)
    requested_timestamp = parse_timestamp_utc(request.timestamp_utc)
    unknown = sorted(set(request.variables) - set(VARIABLES))
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unsupported variables: {', '.join(unknown)}")
    variables = list(dict.fromkeys(request.variables))
    if not variables:
        raise HTTPException(status_code=422, detail="At least one supported variable is required.")
    if requested_timestamp <= TRAINING_END_DATE:
        return historical_v2_payload(request)

    now_step = utc_now_3hour()
    range_end = min(requested_timestamp, now_step)
    range_start = range_end - pd.Timedelta(days=NASA_HISTORY_DAYS)
    try:
        history, cache_used = nasa_client.fetch_history(
            request.latitude,
            request.longitude,
            range_start,
            range_end,
            parameters=VARIABLES,
        )
    except NasaPowerError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if history.empty:
        raise HTTPException(status_code=503, detail="NASA POWER returned no usable history.")

    model = operational_model()
    legacy_data = runtime()
    station_list = legacy_data["stations"]
    nearest = nearest_stations(request.latitude, request.longitude, station_list, k=1)[0]
    correction_anchor_cache: dict[pd.Timestamp, list[tuple[Station, float, pd.Series]]] = {}
    operational_correction_anchor_cache: dict[
        tuple[pd.Timestamp, pd.Timestamp, str],
        list[tuple[Station, float, pd.Series]],
    ] = {}

    def correction_anchors(timestamp: pd.Timestamp) -> list[tuple[Station, float, pd.Series]]:
        timestamp = pd.Timestamp(timestamp)
        if timestamp not in correction_anchor_cache:
            correction_anchor_cache[timestamp] = climatology_anchors_for_correction(
                data=legacy_data,
                latitude=request.latitude,
                longitude=request.longitude,
                timestamp=timestamp,
            )
        return correction_anchor_cache[timestamp]

    def operational_correction_anchors(
        target: pd.Timestamp,
        origin: pd.Timestamp,
        variable: str,
    ) -> list[tuple[Station, float, pd.Series]]:
        key = (pd.Timestamp(target), pd.Timestamp(origin), variable)
        if key not in operational_correction_anchor_cache:
            operational_correction_anchor_cache[key] = operational_anchors_for_correction(
                base_anchors=correction_anchors(target),
                history=history,
                origin=origin,
                target=target,
                variable=variable,
                model=model,
            )
        return operational_correction_anchor_cache[key]
    estimates: dict[str, Any] = {}
    horizons: list[float] = []
    latest_timestamps: list[pd.Timestamp] = []
    available_count = 0
    used_forecast = False

    for variable in variables:
        valid_series = history[variable].dropna()
        valid_series = valid_series.loc[valid_series.index <= range_end]
        if valid_series.empty:
            estimates[variable] = {
                "requested": {
                    "status": "unavailable",
                    "source": "NASA_POWER",
                    "classification": "unavailable",
                    "timestamp_utc": iso_utc(requested_timestamp),
                    "raw_forecast": None,
                    "bmd_equivalent": None,
                    "nasa_raw": None,
                    "bmd_raw": None,
                    "nasa_forecast": None,
                    "bmd_forecast": None,
                    "bmd_actual": None,
                    "bmd_estimate": None,
                    "corrected_nasa": None,
                    "correction_model_version": None,
                    "correction_method": None,
                    "p05": None,
                    "p50": None,
                    "p95": None,
                    "wet_probability": None,
                    "model_version": model.version,
                    "reason": "no_nasa_history_for_variable",
                },
                "latest_nasa": None,
            }
            continue

        latest_timestamp = pd.Timestamp(valid_series.index[-1])
        latest_timestamps.append(latest_timestamp)
        latest_features = build_forecast_features(
            history.loc[:latest_timestamp],
            origin=latest_timestamp,
            target=latest_timestamp,
            latitude=request.latitude,
            longitude=request.longitude,
        )
        latest_prediction = model.predict(variable, latest_features)
        latest_payload = operational_payload(
            variable=variable,
            prediction=latest_prediction,
            timestamp=latest_timestamp,
            source="NASA_POWER_NRT",
            classification="latest_nasa_correction",
            raw_override=float(valid_series.iloc[-1]),
        )
        if latest_payload["status"] == "available":
            apply_previous_correction(
                latest_payload,
                previous_model_correction(
                    data=legacy_data,
                    anchors=operational_correction_anchors(latest_timestamp, latest_timestamp, variable),
                    latitude=request.latitude,
                    longitude=request.longitude,
                    timestamp=latest_timestamp,
                    variable=variable,
                    nasa_value=float(latest_payload["raw_forecast"]),
                ),
            )

        exact_value = history[variable].get(requested_timestamp, np.nan)
        if pd.notna(exact_value):
            correction_origin_timestamp = requested_timestamp
            requested_features = build_forecast_features(
                history.loc[:requested_timestamp],
                origin=requested_timestamp,
                target=requested_timestamp,
                latitude=request.latitude,
                longitude=request.longitude,
            )
            prediction = model.predict(variable, requested_features)
            requested_payload = operational_payload(
                variable=variable,
                prediction=prediction,
                timestamp=requested_timestamp,
                source="NASA_POWER_NRT",
                classification="nasa_exact_correction",
                raw_override=float(exact_value),
            )
            horizon_hours = 0.0
        else:
            horizon_hours = float((requested_timestamp - latest_timestamp) / pd.Timedelta(hours=1))
            correction_origin_timestamp = latest_timestamp
            horizons.append(horizon_hours)
            used_forecast = True
            if horizon_hours < 0 or horizon_hours > MAX_FORECAST_HOURS:
                requested_payload = {
                    "status": "unavailable",
                    "source": "NASA_POWER_forecast",
                    "classification": "provisional_forecast",
                    "timestamp_utc": iso_utc(requested_timestamp),
                    "raw_forecast": None,
                    "bmd_equivalent": None,
                    "nasa_raw": None,
                    "bmd_raw": None,
                    "nasa_forecast": None,
                    "bmd_forecast": None,
                    "bmd_actual": None,
                    "bmd_estimate": None,
                    "corrected_nasa": None,
                    "correction_model_version": None,
                    "correction_method": None,
                    "p05": None,
                    "p50": None,
                    "p95": None,
                    "wet_probability": None,
                    "model_version": model.version,
                    "reason": "forecast_horizon_exceeds_96_hours",
                }
            else:
                requested_features = build_forecast_features(
                    history.loc[:latest_timestamp],
                    origin=latest_timestamp,
                    target=requested_timestamp,
                    latitude=request.latitude,
                    longitude=request.longitude,
                )
                prediction = model.predict(variable, requested_features)
                requested_payload = operational_payload(
                    variable=variable,
                    prediction=prediction,
                    timestamp=requested_timestamp,
                    source="NASA_POWER_forecast",
                    classification="provisional_forecast",
                )
        if requested_payload["status"] == "available":
            apply_previous_correction(
                requested_payload,
                previous_model_correction(
                    data=legacy_data,
                    anchors=operational_correction_anchors(
                        requested_timestamp,
                        correction_origin_timestamp,
                        variable,
                    ),
                    latitude=request.latitude,
                    longitude=request.longitude,
                    timestamp=requested_timestamp,
                    variable=variable,
                    nasa_value=float(requested_payload["raw_forecast"]),
                ),
            )
        if requested_payload["status"] == "available":
            available_count += 1
        requested_payload["forecast_horizon_hours"] = horizon_hours
        latest_payload["forecast_horizon_hours"] = 0.0
        estimates[variable] = {"requested": requested_payload, "latest_nasa": latest_payload}

    status = "complete" if available_count == len(variables) else "partial" if available_count else "unavailable"
    latest_common = min(latest_timestamps) if latest_timestamps else None
    lag_hours = (
        max(0.0, float((now_step - latest_common) / pd.Timedelta(hours=1)))
        if latest_common is not None
        else None
    )
    return {
        "status": status,
        "requested_timestamp_utc": iso_utc(requested_timestamp),
        "latest_nasa_timestamp_utc": iso_utc(latest_common) if latest_common is not None else None,
        "nasa_data_lag_hours": lag_hours,
        "forecast_horizon_hours": max(horizons, default=0.0),
        "mode": "provisional_forecast" if used_forecast else "nasa_exact_correction",
        "location": {"latitude": request.latitude, "longitude": request.longitude},
        "nearest_station": {
            "station_id": nearest[0].station_id,
            "station_name": nearest[0].station_name,
            "latitude": nearest[0].latitude,
            "longitude": nearest[0].longitude,
            "distance_km": nearest[1],
        },
        "estimates": estimates,
        "attribution": [
            "NASA POWER Near Real Time meteorology",
            "Bangladesh Meteorological Department historical observations (2021-2024)",
        ],
        "data_warning": "Provisional forecast - not an observation." if used_forecast else None,
        "cache_used": cache_used,
        "bmd_live_enabled": False,
        "bmd_data_status": {
            "kind": "model_forecast" if used_forecast else "model_estimate",
            "observation_available": False,
            "source": "NASA_BMD_operational_model",
            "archive_start_utc": iso_utc(START_DATE),
            "archive_end_utc": iso_utc(TRAINING_END_DATE),
            "reason": "requested_timestamp_is_outside_local_bmd_observation_archive",
        },
    }
