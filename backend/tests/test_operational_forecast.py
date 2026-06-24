from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.bias_correction_core import inverse_distance_average, inverse_distance_residual
from app.operational_forecast import OperationalForecastModel, build_forecast_features


def history(end: str = "2026-06-22 00:00") -> pd.DataFrame:
    index = pd.date_range(end=pd.Timestamp(end), periods=80, freq="3h")
    return pd.DataFrame(
        {
            "T2M": 28.0,
            "RH2M": 80.0,
            "PRECTOTCORR": 0.0,
            "WS10M": 2.0,
        },
        index=index,
    )


def test_packaged_model_serves_validated_temperature_horizon():
    model = OperationalForecastModel.load(BACKEND_ROOT / "models" / "operational_forecast" / "model_bundle.joblib")
    origin = pd.Timestamp("2026-06-22 00:00")
    target = origin + pd.Timedelta(hours=48)
    features = build_forecast_features(history(), origin=origin, target=target, latitude=23.7, longitude=90.3)
    result = model.predict("T2M", features)
    assert result.status == "available"
    assert result.p05 <= result.p50 <= result.p95


def test_validation_tuned_rainfall_is_served():
    model = OperationalForecastModel.load(BACKEND_ROOT / "models" / "operational_forecast" / "model_bundle.joblib")
    origin = pd.Timestamp("2026-06-22 00:00")
    features = build_forecast_features(
        history(), origin=origin, target=origin + pd.Timedelta(hours=24), latitude=23.7, longitude=90.3
    )
    result = model.predict("PRECTOTCORR", features)
    assert result.status == "available"
    assert result.raw_forecast >= 0
    assert result.bmd_equivalent >= 0
    assert 0 <= result.wet_probability <= 1


def test_humidity_and_nonnegative_variables_are_physically_bounded():
    model = OperationalForecastModel.load(BACKEND_ROOT / "models" / "operational_forecast" / "model_bundle.joblib")
    origin = pd.Timestamp("2026-06-22 00:00")
    features = build_forecast_features(history(), origin=origin, target=origin, latitude=23.7, longitude=90.3)
    humidity = model.predict("RH2M", features)
    wind_features = build_forecast_features(history(), origin=origin, target=origin, latitude=23.7, longitude=90.3)
    wind = model.predict("WS10M", wind_features)
    assert 0 <= humidity.p05 <= 100
    assert 0 <= humidity.p95 <= 100
    assert wind.status == "available"
    assert wind.p05 >= 0


def test_idw_exact_station_value_overrides_other_anchors():
    distances = [0.0, 50.0, 100.0]
    assert inverse_distance_average([32.36, 28.0, 25.0], distances, 150.0) == 32.36
    assert inverse_distance_residual([32.36, 28.0], [31.0, 30.0], distances[:2], 150.0) == pytest.approx(1.36)
