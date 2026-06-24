from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app import main
from app.nasa_power import NasaPowerError


client = TestClient(main.app)


def nasa_history(end: str) -> pd.DataFrame:
    index = pd.date_range(end=pd.Timestamp(end), periods=80, freq="3h")
    return pd.DataFrame(
        {
            "T2M": 29.0,
            "RH2M": 82.0,
            "PRECTOTCORR": 0.0,
            "WS10M": 2.2,
        },
        index=index,
    )


def request(timestamp: str, variables=None):
    return {
        "latitude": 23.766667,
        "longitude": 90.383333,
        "timestamp_utc": timestamp,
        "variables": variables or ["T2M", "RH2M", "PRECTOTCORR", "WS10M"],
    }


@pytest.mark.parametrize("delay_hours", [24, 36, 48])
def test_delayed_nasa_returns_requested_forecast_and_latest_nasa(monkeypatch, delay_hours):
    monkeypatch.setattr(main, "utc_now_3hour", lambda: pd.Timestamp("2026-06-24 06:00"))
    latest = pd.Timestamp("2026-06-24 06:00") - pd.Timedelta(hours=delay_hours)
    monkeypatch.setattr(
        main.nasa_client,
        "fetch_history",
        lambda *_args, **_kwargs: (nasa_history(str(latest)), False),
    )
    response = client.post("/api/v2/estimate", json=request("2026-06-24T06:00:00Z", ["T2M"]))
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "provisional_forecast"
    assert payload["bmd_data_status"]["kind"] == "model_forecast"
    assert payload["bmd_data_status"]["observation_available"] is False
    assert payload["forecast_horizon_hours"] == delay_hours
    assert payload["estimates"]["T2M"]["requested"]["timestamp_utc"] == "2026-06-24T06:00:00Z"
    assert payload["estimates"]["T2M"]["requested"]["nasa_forecast"] is not None
    assert payload["estimates"]["T2M"]["requested"]["bmd_forecast"] is not None
    assert payload["estimates"]["T2M"]["requested"]["corrected_nasa"] is not None
    assert payload["estimates"]["T2M"]["requested"]["correction_model_version"] == "bias-correction-v1"
    assert payload["estimates"]["T2M"]["requested"]["correction_method"] == "anchor_idw_bmd"
    assert payload["estimates"]["T2M"]["requested"]["nasa_raw"] is None
    assert payload["estimates"]["T2M"]["latest_nasa"]["timestamp_utc"] == latest.strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def test_exact_nasa_timestamp_uses_correction_without_forecast(monkeypatch):
    monkeypatch.setattr(main, "utc_now_3hour", lambda: pd.Timestamp("2026-06-24 06:00"))
    monkeypatch.setattr(
        main.nasa_client,
        "fetch_history",
        lambda *_args, **_kwargs: (nasa_history("2026-06-24 06:00"), False),
    )
    response = client.post("/api/v2/estimate", json=request("2026-06-24T06:00:00Z", ["T2M"]))
    payload = response.json()
    assert response.status_code == 200
    assert payload["mode"] == "nasa_exact_correction"
    assert payload["bmd_data_status"]["kind"] == "model_estimate"
    assert payload["forecast_horizon_hours"] == 0
    assert payload["data_warning"] is None
    assert payload["estimates"]["T2M"]["requested"]["nasa_raw"] == 29.0
    assert payload["estimates"]["T2M"]["requested"]["bmd_estimate"] is not None
    assert payload["estimates"]["T2M"]["requested"]["corrected_nasa"] is not None
    assert payload["estimates"]["T2M"]["requested"]["correction_model_version"] == "bias-correction-v1"
    assert payload["estimates"]["T2M"]["requested"]["bmd_raw"] is None


def test_station_marker_uses_exact_operational_bmd_anchor(monkeypatch):
    monkeypatch.setattr(main, "utc_now_3hour", lambda: pd.Timestamp("2026-06-24 06:00"))
    monkeypatch.setattr(
        main.nasa_client,
        "fetch_history",
        lambda *_args, **_kwargs: (nasa_history("2026-06-23 06:00"), False),
    )
    response = client.post(
        "/api/v2/estimate",
        json=request("2026-06-24T06:00:00Z", ["T2M", "RH2M"]),
    )
    assert response.status_code == 200
    estimates = response.json()["estimates"]
    for variable in ("T2M", "RH2M"):
        requested = estimates[variable]["requested"]
        assert requested["correction_method"] == "anchor_idw_bmd"
        assert requested["correction_anchor_station_id"] == "dhaka"
        assert requested["correction_anchor_distance_km"] == pytest.approx(0.0, abs=1e-6)
        assert requested["corrected_nasa"] == pytest.approx(requested["bmd_forecast"])


def test_historical_payload_exposes_bmd_and_nasa_raw_values(monkeypatch):
    monkeypatch.setattr(
        main,
        "correct",
        lambda _request: {
            "requested_timestamp_utc": "2024-06-24T06:00:00Z",
            "resolved_timestamp_utc": "2024-06-24T06:00:00Z",
            "nasa_data_lag_hours": 0.0,
            "location": {"latitude": 23.766667, "longitude": 90.383333},
            "nearest_station": {
                "station_id": "dhaka",
                "station_name": "Dhaka",
                "latitude": 23.766667,
                "longitude": 90.383333,
                "distance_km": 0.0,
            },
            "estimates": {
                "T2M": {
                    "raw_nasa": 31.2,
                    "nearest_bmd_station_value": 30.4,
                    "corrected": 30.6,
                    "uncertainty_residual_p05": -1.0,
                    "uncertainty_residual_p95": 1.0,
                }
            },
            "model": {"version": "test-model"},
        },
    )
    payload = main.historical_v2_payload(
        main.CorrectionRequest(
            latitude=23.766667,
            longitude=90.383333,
            timestamp_utc="2024-06-24T06:00:00Z",
            variables=["T2M"],
        )
    )
    requested = payload["estimates"]["T2M"]["requested"]
    assert payload["bmd_data_status"]["kind"] == "actual_observation"
    assert payload["bmd_data_status"]["observation_available"] is True
    assert requested["nasa_raw"] == 31.2
    assert requested["bmd_raw"] == 30.4
    assert requested["bmd_actual"] == 30.4
    assert requested["bmd_data_kind"] == "actual_observation"
    assert requested["bmd_estimate"] == 30.6
    assert requested["corrected_nasa"] == 30.6
    assert requested["nasa_forecast"] is None
    assert requested["bmd_forecast"] is None


def test_missing_nasa_variable_does_not_disable_other_variables(monkeypatch):
    frame = nasa_history("2026-06-23 06:00")
    frame["RH2M"] = float("nan")
    monkeypatch.setattr(main, "utc_now_3hour", lambda: pd.Timestamp("2026-06-24 06:00"))
    monkeypatch.setattr(main.nasa_client, "fetch_history", lambda *_args, **_kwargs: (frame, False))
    response = client.post("/api/v2/estimate", json=request("2026-06-24T06:00:00Z", ["T2M", "RH2M"]))
    payload = response.json()
    assert payload["status"] == "partial"
    assert payload["estimates"]["T2M"]["requested"]["status"] == "available"
    assert payload["estimates"]["RH2M"]["requested"]["reason"] == "no_nasa_history_for_variable"


def test_nasa_delay_plus_future_request_supports_96_hour_horizon(monkeypatch):
    monkeypatch.setattr(main, "utc_now_3hour", lambda: pd.Timestamp("2026-06-24 06:00"))
    monkeypatch.setattr(
        main.nasa_client,
        "fetch_history",
        lambda *_args, **_kwargs: (nasa_history("2026-06-22 06:00"), False),
    )
    response = client.post("/api/v2/estimate", json=request("2026-06-26T06:00:00Z", ["T2M"]))
    payload = response.json()
    assert response.status_code == 200
    assert payload["forecast_horizon_hours"] == 96
    assert payload["estimates"]["T2M"]["requested"]["status"] == "available"


def test_validation_tuned_rainfall_returns_available_without_fake_climatology(monkeypatch):
    monkeypatch.setattr(main, "utc_now_3hour", lambda: pd.Timestamp("2026-06-24 06:00"))
    monkeypatch.setattr(
        main.nasa_client,
        "fetch_history",
        lambda *_args, **_kwargs: (nasa_history("2026-06-23 06:00"), False),
    )
    response = client.post(
        "/api/v2/estimate",
        json=request("2026-06-24T06:00:00Z", ["T2M", "PRECTOTCORR"]),
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "complete"
    assert payload["estimates"]["PRECTOTCORR"]["requested"]["status"] == "available"
    assert payload["estimates"]["PRECTOTCORR"]["requested"]["wet_probability"] is not None
    assert "climatology" not in response.text.lower()


def test_more_than_96_hours_is_unavailable_but_latest_nasa_is_returned(monkeypatch):
    monkeypatch.setattr(main, "utc_now_3hour", lambda: pd.Timestamp("2026-06-24 06:00"))
    monkeypatch.setattr(
        main.nasa_client,
        "fetch_history",
        lambda *_args, **_kwargs: (nasa_history("2026-06-19 06:00"), False),
    )
    response = client.post("/api/v2/estimate", json=request("2026-06-24T06:00:00Z", ["T2M"]))
    payload = response.json()
    assert payload["status"] == "unavailable"
    assert payload["estimates"]["T2M"]["latest_nasa"] is not None
    assert payload["estimates"]["T2M"]["requested"]["reason"] == "forecast_horizon_exceeds_96_hours"


def test_nasa_outage_without_cache_returns_503(monkeypatch):
    def fail(*_args, **_kwargs):
        raise NasaPowerError("upstream unavailable")

    monkeypatch.setattr(main.nasa_client, "fetch_history", fail)
    response = client.post("/api/v2/estimate", json=request("2026-06-24T06:00:00Z", ["T2M"]))
    assert response.status_code == 503


def test_old_endpoint_rejects_post_2024_operation():
    response = client.post("/api/correct", json=request("2026-06-24T06:00:00Z", ["T2M"]))
    assert response.status_code == 409
