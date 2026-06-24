from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from datetime import timezone
from typing import Any, Callable

import pandas as pd
import requests

from .bias_correction_core import VARIABLES


NASA_POWER_URL = os.getenv(
    "NASA_POWER_URL",
    "https://power.larc.nasa.gov/api/temporal/hourly/point",
)


class NasaPowerError(RuntimeError):
    pass


@dataclass
class CacheEntry:
    created_at: float
    frame: pd.DataFrame


class NasaPowerClient:
    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        cache_ttl_seconds: int = 3600,
        stale_ttl_seconds: int = 86400,
        timeout_seconds: int = 45,
        retries: int = 2,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.session = session or requests.Session()
        self.cache_ttl_seconds = cache_ttl_seconds
        self.stale_ttl_seconds = stale_ttl_seconds
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.clock = clock
        self._cache: dict[tuple[Any, ...], CacheEntry] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(
        latitude: float,
        longitude: float,
        start: pd.Timestamp,
        end: pd.Timestamp,
        parameters: list[str],
    ) -> tuple[Any, ...]:
        return (
            round(latitude, 4),
            round(longitude, 4),
            start.strftime("%Y%m%d"),
            end.strftime("%Y%m%d"),
            tuple(sorted(parameters)),
        )

    def _cached(self, key: tuple[Any, ...], max_age: int) -> pd.DataFrame | None:
        with self._lock:
            entry = self._cache.get(key)
        if entry and self.clock() - entry.created_at <= max_age:
            return entry.frame.copy()
        return None

    def fetch_history(
        self,
        latitude: float,
        longitude: float,
        start: pd.Timestamp,
        end: pd.Timestamp,
        *,
        parameters: list[str] | None = None,
    ) -> tuple[pd.DataFrame, bool]:
        parameters = parameters or VARIABLES.copy()
        start = pd.Timestamp(start).floor("D")
        end = pd.Timestamp(end).floor("D")
        if end < start:
            raise ValueError("NASA POWER range end must be on or after start.")
        key = self._key(latitude, longitude, start, end, parameters)
        cached = self._cached(key, self.cache_ttl_seconds)
        if cached is not None:
            return cached, True

        params = {
            "parameters": ",".join(parameters),
            "community": "RE",
            "longitude": longitude,
            "latitude": latitude,
            "start": start.strftime("%Y%m%d"),
            "end": end.strftime("%Y%m%d"),
            "format": "JSON",
            "time-standard": "UTC",
        }
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self.session.get(NASA_POWER_URL, params=params, timeout=self.timeout_seconds)
                response.raise_for_status()
                frame = self._parse(response.json(), parameters)
                with self._lock:
                    self._cache[key] = CacheEntry(created_at=self.clock(), frame=frame.copy())
                return frame, False
            except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.25 * (2**attempt))

        stale = self._cached(key, self.stale_ttl_seconds)
        if stale is not None:
            return stale, True
        raise NasaPowerError(f"NASA POWER request failed: {last_error}") from last_error

    @staticmethod
    def _parse(payload: dict[str, Any], parameters: list[str]) -> pd.DataFrame:
        source = payload["properties"]["parameter"]
        series_by_variable: dict[str, pd.Series] = {}
        for variable in parameters:
            values = source.get(variable, {})
            parsed: dict[pd.Timestamp, float] = {}
            for key, value in values.items():
                timestamp = pd.to_datetime(key, format="%Y%m%d%H", errors="coerce", utc=True)
                if pd.isna(timestamp):
                    continue
                numeric = pd.to_numeric(value, errors="coerce")
                parsed[timestamp.tz_convert(None)] = float(numeric) if pd.notna(numeric) and float(numeric) > -900 else float("nan")
            series_by_variable[variable] = pd.Series(parsed, dtype=float)
        frame = pd.DataFrame(series_by_variable).sort_index()
        frame.index.name = "timestamp"
        return frame[frame.index.hour.isin(range(0, 24, 3))]


def utc_now_3hour() -> pd.Timestamp:
    now = pd.Timestamp.now(tz=timezone.utc).tz_convert(None)
    return now.floor("3h")
