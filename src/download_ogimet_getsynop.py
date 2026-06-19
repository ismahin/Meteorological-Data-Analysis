from __future__ import annotations

import argparse
import csv
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlencode

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "ground_ogimet"
DEFAULT_REPORT = PROJECT_ROOT / "outputs" / "tables" / "ogimet_getsynop_download_report.csv"

GETSYNOP_URL = "https://www.ogimet.com/cgi-bin/getsynop"
DEFAULT_STATE = "Bang"

DEFAULT_HEADERS = {
    "User-Agent": "OGIMET-getsynop-downloader/1.0 (Python requests; meteorological research)",
}


def parse_utc_datetime(value: str) -> datetime:
    text = value.strip().replace("Z", "+00:00")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
    if "T" not in text and re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{1,2}", text):
        date_part, hour_part = text.split()
        return datetime.fromisoformat(f"{date_part}T{hour_part.zfill(2)}:00:00").replace(
            tzinfo=timezone.utc
        )
    if "T" in text and len(text) <= 16:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def resolve_under_project(path: Path) -> Path:
    return path if path.is_absolute() else (PROJECT_ROOT / path)


def format_getsynop_dt(dt: datetime) -> str:
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y%m%d%H%M")


def iter_inclusive_chunks(
    start: datetime,
    end: datetime,
    *,
    days_per_chunk: int,
) -> Iterator[tuple[datetime, datetime]]:
    if end < start:
        raise ValueError("end_utc must be on or after start_utc.")
    cursor = start
    delta = timedelta(days=days_per_chunk)
    step_back = timedelta(minutes=1)
    while cursor <= end:
        chunk_end = min(cursor + delta - step_back, end)
        yield cursor, chunk_end
        cursor = chunk_end + timedelta(minutes=1)


def chunk_output_path(output_dir: Path, estado: str, begin: datetime, end: datetime) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", estado).strip("_") or "state"
    tag = f"{format_getsynop_dt(begin)}_{format_getsynop_dt(end)}"
    return output_dir / f"ogimet_getsynop_{safe}_{tag}.csv"


def looks_like_getsynop_csv(text: str) -> bool:
    if not text or len(text) < 50:
        return False
    first = text.lstrip("\ufeff").splitlines()[0].lower()
    return ("estacion" in first or "wmoind" in first) and "parte" in first


def request_getsynop(
    session: requests.Session,
    *,
    begin: str,
    end: str,
    state: str,
    lang: str,
    retries: int,
    timeout: int,
) -> str:
    params: dict[str, str] = {
        "begin": begin,
        "end": end,
        "state": state,
        "lang": lang,
        "header": "yes",
    }
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = session.get(GETSYNOP_URL, params=params, timeout=timeout)
            response.raise_for_status()
            text = response.text
            if not looks_like_getsynop_csv(text):
                preview = text[:600].replace("\n", " ")
                raise ValueError(f"Unexpected getsynop response. Preview: {preview}")
            return text
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt == retries:
                break
            sleep_seconds = min(30, 2**attempt)
            print(f"Request failed on attempt {attempt}; retrying in {sleep_seconds}s...")
            time.sleep(sleep_seconds)
    raise RuntimeError(f"OGIMET getsynop request failed after {retries} attempts.") from last_error


def count_synop_rows(csv_text: str) -> int:
    lines = csv_text.strip().splitlines()
    if len(lines) <= 1:
        return 0
    return len(lines) - 1


def download_chunks(
    *,
    session: requests.Session,
    output_dir: Path,
    start: datetime,
    end: datetime,
    days_per_chunk: int,
    state: str,
    lang: str,
    overwrite: bool,
    retries: int,
    timeout: int,
    delay: float,
) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks = list(iter_inclusive_chunks(start, end, days_per_chunk=days_per_chunk))
    rows: list[dict[str, Any]] = []
    for index, (cbegin, cend) in enumerate(chunks, start=1):
        path = chunk_output_path(output_dir, state, cbegin, cend)
        begin_s = format_getsynop_dt(cbegin)
        end_s = format_getsynop_dt(cend)
        url = f"{GETSYNOP_URL}?{urlencode({'begin': begin_s, 'end': end_s, 'state': state, 'lang': lang, 'header': 'yes'})}"
        row: dict[str, Any] = {
            "chunk_index": index,
            "chunks_total": len(chunks),
            "begin_utc": cbegin.isoformat(),
            "end_utc": cend.isoformat(),
            "state": state,
            "request_url": url,
            "output_file": str(path.relative_to(PROJECT_ROOT)),
            "status": "",
            "synop_rows": "",
            "bytes": "",
            "message": "",
        }
        if path.exists() and not overwrite:
            body = path.read_text(encoding="utf-8", errors="replace")
            row.update(
                {
                    "status": "skipped_existing",
                    "synop_rows": count_synop_rows(body),
                    "bytes": len(body.encode("utf-8")),
                }
            )
            print(f"[{index}/{len(chunks)}] Skip existing: {path.name}")
            rows.append(row)
            continue
        try:
            text = request_getsynop(
                session,
                begin=begin_s,
                end=end_s,
                state=state,
                lang=lang,
                retries=retries,
                timeout=timeout,
            )
            path.write_text(text, encoding="utf-8", newline="\n")
            n = count_synop_rows(text)
            row.update(
                {
                    "status": "downloaded",
                    "synop_rows": n,
                    "bytes": len(text.encode("utf-8")),
                }
            )
            print(f"[{index}/{len(chunks)}] Downloaded: {path.name} ({n} synop rows)")
        except Exception as exc:
            row.update({"status": "failed", "message": str(exc)})
            print(f"[{index}/{len(chunks)}] Failed: {exc}")
        rows.append(row)
        if index < len(chunks) and delay > 0:
            time.sleep(delay)
    return rows


def write_report(report_path: Path, rows: list[dict[str, Any]]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "chunk_index",
        "chunks_total",
        "begin_utc",
        "end_utc",
        "state",
        "request_url",
        "output_file",
        "status",
        "synop_rows",
        "bytes",
        "message",
    ]
    with report_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Download historical SYNOP via OGIMET getsynop (CSV: WMO, time, raw PARTE). "
            "Use this for multi-year archives; display_synopsc2.php often returns empty for past years."
        )
    )
    parser.add_argument(
        "--start-utc",
        required=True,
        help="Interval start UTC, e.g. 2021-01-01 or 2021-01-01T00.",
    )
    parser.add_argument(
        "--end-utc",
        required=True,
        help="Interval end UTC (inclusive), e.g. 2024-12-31T23.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--state", default=DEFAULT_STATE, help="Country prefix for OGIMET state= (default: Bang).")
    parser.add_argument("--lang", default="eng", help="getsynop lang= (default: eng).")
    parser.add_argument(
        "--days-per-chunk",
        type=int,
        default=7,
        help="Each request covers this many calendar days (default: 7). Reduce if timeouts occur.",
    )
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds between chunk requests.")
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    output_dir = resolve_under_project(args.output_dir)
    report_path = resolve_under_project(args.report)
    start = parse_utc_datetime(args.start_utc)
    end = parse_utc_datetime(args.end_utc)

    print(
        f"OGIMET getsynop: {start.isoformat()} .. {end.isoformat()} (UTC), "
        f"state={args.state!r}, days_per_chunk={args.days_per_chunk}"
    )

    with requests.Session() as session:
        session.headers.update(DEFAULT_HEADERS)
        report_rows = download_chunks(
            session=session,
            output_dir=output_dir,
            start=start,
            end=end,
            days_per_chunk=args.days_per_chunk,
            state=args.state,
            lang=args.lang,
            overwrite=args.overwrite,
            retries=args.retries,
            timeout=args.timeout,
            delay=args.delay,
        )

    write_report(report_path, report_rows)
    ok = sum(1 for r in report_rows if r["status"] == "downloaded")
    sk = sum(1 for r in report_rows if r["status"] == "skipped_existing")
    bad = sum(1 for r in report_rows if r["status"] == "failed")
    print(f"Done. downloaded={ok}, skipped_existing={sk}, failed={bad}, report={report_path}")


if __name__ == "__main__":
    main()
