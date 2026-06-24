from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import requests


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.nasa_power import NasaPowerClient, NasaPowerError


class FakeResponse:
    def __init__(self, payload, *, error: Exception | None = None):
        self.payload = payload
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, *_args, **_kwargs):
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def payload():
    values = {"2026062200": 30.0, "2026062201": 31.0, "2026062203": -999.0}
    return {"properties": {"parameter": {"T2M": values}}}


def test_range_fetch_filters_to_three_hour_steps_and_missing_values():
    session = FakeSession([FakeResponse(payload())])
    client = NasaPowerClient(session=session, retries=0)
    frame, cache_used = client.fetch_history(
        23.7,
        90.3,
        pd.Timestamp("2026-06-22"),
        pd.Timestamp("2026-06-22"),
        parameters=["T2M"],
    )
    assert cache_used is False
    assert list(frame.index) == [pd.Timestamp("2026-06-22 00:00"), pd.Timestamp("2026-06-22 03:00")]
    assert frame.loc[pd.Timestamp("2026-06-22 00:00"), "T2M"] == 30.0
    assert pd.isna(frame.loc[pd.Timestamp("2026-06-22 03:00"), "T2M"])


def test_fresh_cache_avoids_second_network_request():
    session = FakeSession([FakeResponse(payload())])
    client = NasaPowerClient(session=session, retries=0)
    args = (23.7, 90.3, pd.Timestamp("2026-06-22"), pd.Timestamp("2026-06-22"))
    client.fetch_history(*args, parameters=["T2M"])
    _, cache_used = client.fetch_history(*args, parameters=["T2M"])
    assert cache_used is True
    assert session.calls == 1


def test_provider_failure_uses_bounded_stale_cache():
    now = [100.0]
    session = FakeSession([FakeResponse(payload()), requests.ConnectionError("offline")])
    client = NasaPowerClient(
        session=session,
        retries=0,
        cache_ttl_seconds=10,
        stale_ttl_seconds=100,
        clock=lambda: now[0],
    )
    args = (23.7, 90.3, pd.Timestamp("2026-06-22"), pd.Timestamp("2026-06-22"))
    client.fetch_history(*args, parameters=["T2M"])
    now[0] = 120.0
    frame, cache_used = client.fetch_history(*args, parameters=["T2M"])
    assert cache_used is True
    assert not frame.empty
    assert session.calls == 2
