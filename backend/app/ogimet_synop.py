from __future__ import annotations

import csv
import math
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import timezone
from io import StringIO
from typing import Any, Callable

import pandas as pd
import requests

from .bias_correction_core import VARIABLES


OGIMET_GETSYNOP_URL = os.getenv("OGIMET_GETSYNOP_URL", "https://www.ogimet.com/cgi-bin/getsynop")
DEFAULT_OGIMET_STATE = os.getenv("OGIMET_STATE", "Bang")

# OGIMET/WMO station ids for the 35-station BMD study set.
WMO_TO_STATION_ID: dict[str, str] = {
    "41858": "sydpur",
    "41859": "rangpur",
    "41863": "dinajpur",
    "41883": "bogra",
    "41886": "mymensingh",
    "41891": "sylhet",
    "41895": "rajshahi",
    "41907": "ishurdi",
    "41909": "tangail",
    "41915": "srimangal",
    "41923": "dhaka",
    "41926": "chuadanga",
    "41929": "faridpur",
    "41933": "comilla",
    "41936": "jessore",
    "41939": "madaripur",
    "41941": "chandpur",
    "41943": "feni",
    "41946": "satkhira",
    "41947": "khulna",
    "41950": "barisal",
    "41951": "bhola",
    "41953": "m_court",
    "41958": "mongla",
    "41960": "patuakhali",
    "41963": "hatiya",
    "41964": "sandwip",
    "41965": "sitakunda",
    "41966": "rangamati",
    "41977": "ambagan_ctg",
    "41978": "chittagong",
    "41984": "khepupara",
    "41989": "kutubdia",
    "41992": "cox_s_bazar",
    "41998": "teknaf",
}
STATION_ID_TO_WMO = {station_id: wmo for wmo, station_id in WMO_TO_STATION_ID.items()}

TOKEN_RE = re.compile(r"[^\s=]+")


class OgimetSynopError(RuntimeError):
    pass


@dataclass(frozen=True)
class StationObservation:
    station_id: str
    wmo_id: str
    timestamp_utc: pd.Timestamp
    values: dict[str, float]
    raw_report: str
    source_url: str | None = None


@dataclass
class _CacheEntry:
    created_at: float
    observations: dict[str, StationObservation]


def _relative_temperature(token: str) -> float | None:
    if len(token) != 5 or token[0] not in "12" or "/" in token:
        return None
    sign = -1.0 if token[1] == "1" else 1.0
    try:
        return sign * int(token[2:5]) / 10.0
    except ValueError:
        return None


def _magnus_rh_percent(t_c: float | None, td_c: float | None) -> float | None:
    if t_c is None or td_c is None or math.isnan(t_c) or math.isnan(td_c):
        return None
    if td_c > t_c + 0.2:
        return None
    es = 6.112 * math.exp((17.67 * t_c) / (t_c + 243.5))
    e = 6.112 * math.exp((17.67 * td_c) / (td_c + 243.5))
    if es <= 0:
        return None
    return max(0.0, min(100.0, 100.0 * e / es))


def _parse_yyggiw_iw(yyggiw: str) -> int:
    if len(yyggiw) < 5:
        return 4
    for candidate in (yyggiw[-1], yyggiw[3]):
        if candidate.isdigit() and 0 <= int(candidate) <= 8:
            return int(candidate)
    return 4


def _parse_nddff(token: str) -> tuple[int, int, int] | None:
    token = token.rstrip("/")
    if len(token) != 5 or not token.isdigit():
        return None
    n, dd, ff = int(token[0]), int(token[1:3]), int(token[3:5])
    if not (0 <= n <= 9):
        return None
    if dd not in (0, 99) and not (1 <= dd <= 36):
        return None
    return n, dd, ff


def _wind_speed_ms(ff: int, iw: int) -> float:
    if iw == 0:
        return 2.0 * ff
    if iw in (1, 4):
        return 0.1 * ff
    if iw == 2:
        return 0.514444 * ff
    if iw == 3:
        return ff / 3.6
    if iw == 5:
        return 0.2 * ff
    if iw == 6:
        return 0.514444 * ff * 2.0
    if iw == 7:
        return 0.514444 * ff * 3.0
    if iw == 8:
        return 0.514444 * ff * 4.0
    return 0.1 * ff


def _tokens_section1(tokens: list[str]) -> list[str]:
    try:
        return tokens[: tokens.index("333")]
    except ValueError:
        return tokens


def _precip_mm_from_6_group(token: str) -> tuple[float | None, int | None]:
    if len(token) != 5 or not token.startswith("6") or not token[1:].isdigit():
        return None, None
    rrr = int(token[1:4])
    tr = int(token[4])
    if tr == 0:
        return None, None
    if rrr == 999:
        return None, tr
    if rrr == 990:
        return 0.0, tr
    if 990 < rrr <= 998:
        return (rrr - 990) / 10.0, tr
    if rrr == 0:
        return 0.0, tr
    return rrr / 10.0, tr


_TR_SORT_KEY = {7: 0, 5: 1, 6: 2, 1: 3, 2: 4, 3: 5, 4: 6, 8: 7, 9: 8}


def _precipitation_mm(s1: list[str], tokens: list[str], nddff_tok: str | None) -> float | None:
    if len(s1) > 4 and s1[4] and s1[4][0].isdigit():
        ir = int(s1[4][0])
        if ir == 3:
            return 0.0
        if ir == 4:
            return None
    skip = {nddff_tok} if nddff_tok else set()
    candidates: list[tuple[int, float]] = []
    for token in tokens:
        if token in skip:
            continue
        amount, tr = _precip_mm_from_6_group(token)
        if amount is None or tr is None:
            continue
        candidates.append((_TR_SORT_KEY.get(tr, 50), amount))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def decode_synop_report(report: str, timestamp: pd.Timestamp) -> dict[str, float]:
    """Decode one OGIMET FM-12 SYNOP report into project variables.

    OGIMET provides SYNOP rows in UTC. This function keeps the timestamp external and
    only decodes meteorological values; it does not shift time or resample data.
    """
    tokens = ["000000000000", *TOKEN_RE.findall(report.replace("NIL=", " NIL "))]
    values = {variable: float("nan") for variable in VARIABLES}
    if len(tokens) < 4 or tokens[1] != "AAXX" or "NIL" in tokens:
        return values

    yyggiw = tokens[2]
    iw = _parse_yyggiw_iw(yyggiw)
    s1 = _tokens_section1(tokens)
    nddff_tok = s1[5] if len(s1) > 5 and _parse_nddff(s1[5]) else None
    scan_start = 6 if nddff_tok else 4
    t2m: float | None = None
    tdew: float | None = None
    for token in s1[scan_start : scan_start + 12]:
        if token.startswith("1") and t2m is None:
            t2m = _relative_temperature(token)
        elif token.startswith("2") and tdew is None:
            tdew = _relative_temperature(token)

    if t2m is not None:
        values["T2M"] = t2m
    rh = _magnus_rh_percent(t2m, tdew)
    if rh is not None:
        values["RH2M"] = rh
    if nddff_tok:
        parsed = _parse_nddff(nddff_tok)
        if parsed:
            values["WS10M"] = _wind_speed_ms(parsed[2], iw)
    precip = _precipitation_mm(s1, tokens, nddff_tok)
    if precip is not None:
        values["PRECTOTCORR"] = precip

    return values


def parse_getsynop_csv_text(csv_text: str, *, source_url: str | None = None) -> dict[str, StationObservation]:
    observations: dict[str, StationObservation] = {}
    reader = csv.DictReader(StringIO(csv_text.lstrip("\ufeff")))
    for row in reader:
        norm = {((key or "").strip().upper()): ((value or "").strip()) for key, value in row.items()}
        wmo_raw = norm.get("WMO_ID") or norm.get("ESTACION") or norm.get("WMOIND") or ""
        report = norm.get("PARTE") or norm.get("REPORT") or ""
        if not wmo_raw or not report:
            continue
        try:
            wmo_id = str(int(wmo_raw))
            timestamp = pd.Timestamp(
                year=int(norm["ANO"]),
                month=int(norm["MES"]),
                day=int(norm["DIA"]),
                hour=int(norm["HORA"]),
                minute=int(norm.get("MINUTO") or "0"),
                tz=timezone.utc,
            ).tz_convert(None)
        except (KeyError, ValueError):
            continue
        station_id = WMO_TO_STATION_ID.get(wmo_id)
        if not station_id:
            continue
        observations[station_id] = StationObservation(
            station_id=station_id,
            wmo_id=wmo_id,
            timestamp_utc=timestamp,
            values=decode_synop_report(report, timestamp),
            raw_report=report,
            source_url=source_url,
        )
    return observations


class OgimetSynopClient:
    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        enabled: bool = True,
        state: str = DEFAULT_OGIMET_STATE,
        cache_ttl_seconds: int = 600,
        timeout_seconds: int = 20,
        retries: int = 1,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.session = session or requests.Session()
        self.session.headers.setdefault(
            "User-Agent",
            "NASA-BMD-operational-forecast/1.0 (OGIMET SYNOP UTC lookup)",
        )
        self.enabled = enabled
        self.state = state
        self.cache_ttl_seconds = cache_ttl_seconds
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.clock = clock
        self._cache: dict[str, _CacheEntry] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _timestamp_key(timestamp: pd.Timestamp) -> str:
        return pd.Timestamp(timestamp).strftime("%Y%m%d%H%M")

    def _cached(self, key: str) -> dict[str, StationObservation] | None:
        with self._lock:
            entry = self._cache.get(key)
        if entry and self.clock() - entry.created_at <= self.cache_ttl_seconds:
            return dict(entry.observations)
        return None

    def fetch_country_hour(self, timestamp: pd.Timestamp) -> dict[str, StationObservation]:
        if not self.enabled:
            return {}
        timestamp = pd.Timestamp(timestamp)
        if timestamp.minute or timestamp.second or timestamp.microsecond:
            raise ValueError("OGIMET SYNOP timestamp must be an exact UTC hour.")
        key = self._timestamp_key(timestamp)
        cached = self._cached(key)
        if cached is not None:
            return cached

        params = {
            "begin": key,
            "end": key,
            "state": self.state,
            "lang": "eng",
            "header": "yes",
        }
        source_url = requests.Request("GET", OGIMET_GETSYNOP_URL, params=params).prepare().url
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self.session.get(OGIMET_GETSYNOP_URL, params=params, timeout=self.timeout_seconds)
                response.raise_for_status()
                observations = parse_getsynop_csv_text(response.text, source_url=source_url)
                with self._lock:
                    self._cache[key] = _CacheEntry(created_at=self.clock(), observations=dict(observations))
                return observations
            except (requests.RequestException, csv.Error, ValueError, KeyError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.5 * (2**attempt))
        raise OgimetSynopError(f"OGIMET SYNOP request failed: {last_error}") from last_error

    def fetch_station_observation(self, station_id: str, timestamp: pd.Timestamp) -> StationObservation | None:
        return self.fetch_country_hour(timestamp).get(station_id)
