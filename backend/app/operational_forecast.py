from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .bias_correction_core import RAIN_THRESHOLD_MM, VARIABLES, season_code


FORECAST_VERSION = "nasa-bmd-operational-v2"
MAX_FORECAST_HOURS = 96
STEP_HOURS = 3
LAG_STEPS = (0, 1, 2, 8, 16, 56)
ROLLING_WINDOWS = (8, 56)
HORIZON_BUCKETS = ((0, 8, "0-24"), (9, 16, "27-48"), (17, 24, "51-72"), (25, 32, "75-96"))


def feature_columns() -> list[str]:
    columns = [
        "latitude",
        "longitude",
        "origin_month",
        "origin_hour",
        "origin_season",
        "origin_sin_month",
        "origin_cos_month",
        "origin_sin_hour",
        "origin_cos_hour",
        "target_month",
        "target_hour",
        "target_season",
        "target_sin_month",
        "target_cos_month",
        "target_sin_hour",
        "target_cos_hour",
        "horizon_steps",
        "horizon_hours",
    ]
    for variable in VARIABLES:
        columns.extend(f"{variable}_lag_{lag}" for lag in LAG_STEPS)
        for window in ROLLING_WINDOWS:
            columns.extend((f"{variable}_mean_{window}", f"{variable}_std_{window}"))
    return columns


FEATURE_COLUMNS = feature_columns()


def horizon_bucket(horizon_steps: int) -> str | None:
    for start, end, label in HORIZON_BUCKETS:
        if start <= horizon_steps <= end:
            return label
    return None


def _cyclic(value: float, period: float) -> tuple[float, float]:
    angle = 2 * math.pi * value / period
    return math.sin(angle), math.cos(angle)


def build_forecast_features(
    history: pd.DataFrame,
    *,
    origin: pd.Timestamp,
    target: pd.Timestamp,
    latitude: float,
    longitude: float,
) -> dict[str, float]:
    horizon_hours = float((target - origin) / pd.Timedelta(hours=1))
    horizon_steps = int(round(horizon_hours / STEP_HOURS))
    origin_sin_month, origin_cos_month = _cyclic(float(origin.month), 12.0)
    origin_sin_hour, origin_cos_hour = _cyclic(float(origin.hour), 24.0)
    target_sin_month, target_cos_month = _cyclic(float(target.month), 12.0)
    target_sin_hour, target_cos_hour = _cyclic(float(target.hour), 24.0)
    row: dict[str, float] = {
        "latitude": float(latitude),
        "longitude": float(longitude),
        "origin_month": float(origin.month),
        "origin_hour": float(origin.hour),
        "origin_season": float(season_code(int(origin.month))),
        "origin_sin_month": origin_sin_month,
        "origin_cos_month": origin_cos_month,
        "origin_sin_hour": origin_sin_hour,
        "origin_cos_hour": origin_cos_hour,
        "target_month": float(target.month),
        "target_hour": float(target.hour),
        "target_season": float(season_code(int(target.month))),
        "target_sin_month": target_sin_month,
        "target_cos_month": target_cos_month,
        "target_sin_hour": target_sin_hour,
        "target_cos_hour": target_cos_hour,
        "horizon_steps": float(horizon_steps),
        "horizon_hours": horizon_hours,
    }
    ordered = history.sort_index()
    for variable in VARIABLES:
        series = pd.to_numeric(ordered.get(variable, pd.Series(dtype=float)), errors="coerce")
        for lag in LAG_STEPS:
            timestamp = origin - pd.Timedelta(hours=lag * STEP_HOURS)
            value = series.get(timestamp, np.nan)
            row[f"{variable}_lag_{lag}"] = float(value) if pd.notna(value) else math.nan
        upto_origin = series.loc[:origin]
        for window in ROLLING_WINDOWS:
            values = upto_origin.tail(window).dropna()
            row[f"{variable}_mean_{window}"] = float(values.mean()) if not values.empty else math.nan
            row[f"{variable}_std_{window}"] = float(values.std(ddof=0)) if len(values) > 1 else 0.0
    return row


def clamp_value(variable: str, value: float) -> float:
    if not math.isfinite(float(value)):
        return 0.0
    if variable == "RH2M":
        return max(0.0, min(100.0, float(value)))
    if variable in {"PRECTOTCORR", "WS10M"}:
        return max(0.0, float(value))
    return float(value)


@dataclass(frozen=True)
class ForecastResult:
    status: str
    raw_forecast: float | None
    bmd_equivalent: float | None
    p05: float | None
    p50: float | None
    p95: float | None
    wet_probability: float | None
    model_version: str
    reason: str | None = None


class OperationalForecastModel:
    def __init__(self, bundle: dict[str, Any]):
        self.bundle = bundle
        self.version = str(bundle.get("version", FORECAST_VERSION))

    @classmethod
    def load(cls, path: Path) -> "OperationalForecastModel":
        if not path.exists():
            raise FileNotFoundError(f"Missing operational forecast artifact: {path}")
        return cls(joblib.load(path))

    def _quantiles(self, variable: str, bucket: str, season: int) -> tuple[float, float, float]:
        table = self.bundle.get("residual_quantiles", {}).get(variable, {})
        values = table.get(f"{bucket}|{season}") or table.get(f"{bucket}|all") or table.get("all|all")
        if not values:
            return 0.0, 0.0, 0.0
        return float(values["p05"]), float(values["p50"]), float(values["p95"])

    def predict(
        self,
        variable: str,
        features: dict[str, float],
    ) -> ForecastResult:
        horizon_steps = int(round(features["horizon_steps"]))
        bucket = horizon_bucket(horizon_steps)
        if bucket is None:
            return ForecastResult(
                status="unavailable",
                raw_forecast=None,
                bmd_equivalent=None,
                p05=None,
                p50=None,
                p95=None,
                wet_probability=None,
                model_version=self.version,
                reason="forecast_horizon_exceeds_96_hours",
            )
        enabled = self.bundle.get("enabled_horizons", {}).get(variable, {}).get(bucket, False)
        if not enabled:
            return ForecastResult(
                status="unavailable",
                raw_forecast=None,
                bmd_equivalent=None,
                p05=None,
                p50=None,
                p95=None,
                wet_probability=None,
                model_version=self.version,
                reason="validation_failed_for_variable_horizon",
            )
        frame = pd.DataFrame([features], columns=self.bundle["feature_columns"])
        nasa_model = self.bundle.get("nasa_models", {}).get(variable)
        raw = (
            clamp_value(variable, float(nasa_model.predict(frame)[0]))
            if nasa_model is not None
            else clamp_value(variable, features.get(f"{variable}_lag_0", math.nan))
        )
        wet_probability: float | None = None
        if variable == "PRECTOTCORR":
            classifier, regressor = self.bundle["models"][variable]
            wet_probability = float(classifier.predict_proba(frame)[0, 1])
            amount = float(np.expm1(regressor.predict(frame)[0]))
            wet_threshold = float(
                self.bundle.get("rain_probability_thresholds", {}).get(bucket, 0.5)
            )
            prediction = amount if wet_probability >= wet_threshold else 0.0
        else:
            prediction = float(self.bundle["models"][variable].predict(frame)[0])
        q05, q50, q95 = self._quantiles(variable, bucket, int(features["target_season"]))
        point = clamp_value(variable, prediction + q50)
        lower = clamp_value(variable, prediction + q05)
        upper = clamp_value(variable, prediction + q95)
        if lower > upper:
            lower, upper = upper, lower
        return ForecastResult(
            status="available",
            raw_forecast=raw,
            bmd_equivalent=point,
            p05=lower,
            p50=point,
            p95=upper,
            wet_probability=wet_probability,
            model_version=self.version,
        )


class BmdObservationProvider:
    """Disabled boundary for a future documented BMD observation API."""

    enabled = False

    def latest(self, *_: Any, **__: Any) -> None:
        return None
