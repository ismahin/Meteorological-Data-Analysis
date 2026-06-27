from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.ogimet_synop import OgimetSynopClient, parse_getsynop_csv_text


SAMPLE_GETSYNOP = """WMO_ID,ANO,MES,DIA,HORA,MINUTO,PARTE
41923,2026,06,27,00,00,AAXX 27004 41923 32980 00000 10280 20260 30039 40046 72522 333 59013 70000==
"""


def test_parse_getsynop_csv_text_keeps_ogimet_time_as_utc():
    observations = parse_getsynop_csv_text(SAMPLE_GETSYNOP, source_url="https://example.test")
    observation = observations["dhaka"]
    assert observation.wmo_id == "41923"
    assert observation.timestamp_utc == pd.Timestamp("2026-06-27 00:00")
    assert observation.values["T2M"] == pytest.approx(28.0)
    assert observation.values["RH2M"] == pytest.approx(88.9, abs=0.2)
    assert observation.values["WS10M"] == pytest.approx(0.0)
    assert observation.raw_report.startswith("AAXX 27004 41923")


def test_ogimet_client_queries_exact_utc_hour_without_local_shift():
    class FakeResponse:
        text = SAMPLE_GETSYNOP

        def raise_for_status(self):
            return None

    class FakeSession:
        headers = {}

        def __init__(self):
            self.calls = []

        def get(self, url, *, params, timeout):
            self.calls.append((url, params, timeout))
            return FakeResponse()

    session = FakeSession()
    client = OgimetSynopClient(session=session, retries=0, timeout_seconds=7)
    observation = client.fetch_station_observation("dhaka", pd.Timestamp("2026-06-27 00:00"))
    assert observation is not None
    assert session.calls[0][1]["begin"] == "202606270000"
    assert session.calls[0][1]["end"] == "202606270000"
    assert session.calls[0][1]["state"] == "Bang"
