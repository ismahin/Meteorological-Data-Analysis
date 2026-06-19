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
DEFAULT_REPORT = PROJECT_ROOT / "outputs" / "tables" / "ogimet_synop_download_report.csv"

OGIMET_SYNOP_URL = "https://www.ogimet.com/display_synopsc2.php"

# Browser-like User-Agent; some sites block generic python-requests defaults.
DEFAULT_HEADERS = {
    "User-Agent": "OGIMET-synop-downloader/1.0 (Python requests; meteorological research)",
}


def parse_utc_datetime(value: str) -> datetime:
    """Parse 'YYYY-MM-DD', 'YYYY-MM-DDTHH', or 'YYYY-MM-DDTHH:MM' (and optional 'Z') as UTC."""
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


def ogimet_form_fields(
    start: datetime,
    end: datetime,
    *,
    lang: str,
    estado: str,
    tipo: str,
    ord_: str,
    nil: str,
    fmt: str,
) -> dict[str, str]:
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)
    return {
        "lang": lang,
        "estado": estado,
        "tipo": tipo,
        "ord": ord_,
        "nil": nil,
        "fmt": fmt,
        "ano": str(start.year),
        "mes": f"{start.month:02d}",
        "day": f"{start.day:02d}",
        "hora": str(start.hour),
        "anof": str(end.year),
        "mesf": f"{end.month:02d}",
        "dayf": f"{end.day:02d}",
        "horaf": str(end.hour),
        "send": "send",
    }


def build_get_url(fields: dict[str, str]) -> str:
    return f"{OGIMET_SYNOP_URL}?{urlencode(fields)}"


def iter_time_chunks(
    start: datetime,
    end: datetime,
    max_hours: int | None,
) -> Iterator[tuple[datetime, datetime]]:
    if end <= start:
        raise ValueError("end_utc must be after start_utc.")
    if max_hours is None or max_hours <= 0:
        yield start, end
        return
    cursor = start
    step = timedelta(hours=max_hours)
    while cursor < end:
        chunk_end = min(cursor + step, end)
        yield cursor, chunk_end
        cursor = chunk_end


def looks_like_synop_dump(text: str) -> bool:
    if not text or len(text) < 200:
        return False
    lower = text.lower()
    if "<html" in lower and "synop" not in lower[:500]:
        return False
    return "query made at" in lower or "synops from" in lower or "aaxx" in lower


def request_ogimet(
    session: requests.Session,
    fields: dict[str, str],
    *,
    retries: int,
    timeout: int,
) -> str:
    last_error: Exception | None = None
    url = OGIMET_SYNOP_URL
    for attempt in range(1, retries + 1):
        try:
            response = session.get(url, params=fields, timeout=timeout)
            response.raise_for_status()
            text = response.text
            if not looks_like_synop_dump(text):
                preview = text[:800].replace("\n", " ")
                raise ValueError(f"Unexpected OGIMET response (not a SYNOP text dump). Preview: {preview}")
            return text
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt == retries:
                break
            sleep_seconds = min(30, 2**attempt)
            print(f"Request failed on attempt {attempt}; retrying in {sleep_seconds}s...")
            time.sleep(sleep_seconds)
    raise RuntimeError(f"OGIMET request failed after {retries} attempts.") from last_error


def default_chunk_path(output_dir: Path, estado: str, start: datetime, end: datetime) -> Path:
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)
    safe_estado = re.sub(r"[^a-zA-Z0-9_-]+", "_", estado).strip("_") or "country"
    tag = f"{start.strftime('%Y%m%d%H')}_{end.strftime('%Y%m%d%H')}"
    return output_dir / f"ogimet_synop_{safe_estado}_{tag}_UTC.txt"


def download_chunks(
    *,
    session: requests.Session,
    output_dir: Path,
    start: datetime,
    end: datetime,
    max_hours: int | None,
    estado: str,
    lang: str,
    tipo: str,
    ord_: str,
    nil: str,
    fmt: str,
    overwrite: bool,
    retries: int,
    timeout: int,
    delay: float,
) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    chunks = list(iter_time_chunks(start, end, max_hours))
    for index, (chunk_start, chunk_end) in enumerate(chunks, start=1):
        path = default_chunk_path(output_dir, estado, chunk_start, chunk_end)
        fields = ogimet_form_fields(
            chunk_start,
            chunk_end,
            lang=lang,
            estado=estado,
            tipo=tipo,
            ord_=ord_,
            nil=nil,
            fmt=fmt,
        )
        request_url = build_get_url(fields)
        row: dict[str, Any] = {
            "chunk_index": index,
            "chunks_total": len(chunks),
            "start_utc": chunk_start.isoformat(),
            "end_utc": chunk_end.isoformat(),
            "estado": estado,
            "request_url": request_url,
            "output_file": str(path.relative_to(PROJECT_ROOT)),
            "status": "",
            "bytes": "",
            "lines": "",
            "message": "",
        }
        if path.exists() and not overwrite:
            text = path.read_text(encoding="utf-8", errors="replace")
            row.update(
                {
                    "status": "skipped_existing",
                    "bytes": len(text.encode("utf-8")),
                    "lines": text.count("\n") + (1 if text and not text.endswith("\n") else 0),
                }
            )
            print(f"[{index}/{len(chunks)}] Skip existing: {path.name}")
            rows.append(row)
            continue
        try:
            text = request_ogimet(session, fields, retries=retries, timeout=timeout)
            path.write_text(text, encoding="utf-8", newline="\n")
            row.update(
                {
                    "status": "downloaded",
                    "bytes": len(text.encode("utf-8")),
                    "lines": text.count("\n") + (1 if text and not text.endswith("\n") else 0),
                }
            )
            print(f"[{index}/{len(chunks)}] Downloaded: {path.name} ({row['lines']} lines)")
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
        "start_utc",
        "end_utc",
        "estado",
        "request_url",
        "output_file",
        "status",
        "bytes",
        "lines",
        "message",
    ]
    with report_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def resolve_under_project(path: Path) -> Path:
    return path if path.is_absolute() else (PROJECT_ROOT / path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Download OGIMET country SYNOP listings as plain text (fmt=txt). "
            "Default country filter matches the Bangladesh form: estado=Bang. "
            "OGIMET may expand the requested window slightly on the server side."
        )
    )
    parser.add_argument(
        "--start-utc",
        required=True,
        help="Interval start in UTC, e.g. 2026-05-09, 2026-05-09T10, or 2026-05-09T10:00:00.",
    )
    parser.add_argument(
        "--end-utc",
        required=True,
        help="Interval end in UTC (same formats as --start-utc).",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--estado",
        default="Bang",
        help="OGIMET country filter (default: Bang for Bangladesh, matches 'Bang*').",
    )
    parser.add_argument("--lang", default="en")
    parser.add_argument("--tipo", default="SI", help="SYNOP output option (default: SI).")
    parser.add_argument("--ord", dest="ord_", default="REV", help="Sort order (default: REV, newest first).")
    parser.add_argument(
        "--nil",
        default="NO",
        help="OGIMET nil= parameter: NO omits NIL/missing reports (default); SI includes them.",
    )
    parser.add_argument("--fmt", default="txt", choices=["txt"], help="Only 'txt' is wired for now.")
    parser.add_argument(
        "--max-hours-per-request",
        type=int,
        default=168,
        help=(
            "Split the UTC interval into chunks of at most this many hours (default: 168 = 7 days). "
            "Use 0 for a single request covering the full interval (may fail for long ranges)."
        ),
    )
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds between chunk requests.")
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    output_dir = resolve_under_project(args.output_dir)
    report_path = resolve_under_project(args.report)

    start = parse_utc_datetime(args.start_utc)
    end = parse_utc_datetime(args.end_utc)
    max_hours = args.max_hours_per_request if args.max_hours_per_request > 0 else None

    print(
        f"OGIMET SYNOP download: {start.isoformat()} .. {end.isoformat()} (UTC), "
        f"estado={args.estado!r}, max_hours_per_request={max_hours!r}"
    )

    with requests.Session() as session:
        session.headers.update(DEFAULT_HEADERS)
        rows = download_chunks(
            session=session,
            output_dir=output_dir,
            start=start,
            end=end,
            max_hours=max_hours,
            estado=args.estado,
            lang=args.lang,
            tipo=args.tipo,
            ord_=args.ord_,
            nil=args.nil,
            fmt=args.fmt,
            overwrite=args.overwrite,
            retries=args.retries,
            timeout=args.timeout,
            delay=args.delay,
        )

    write_report(report_path, rows)
    downloaded = sum(1 for row in rows if row["status"] == "downloaded")
    skipped = sum(1 for row in rows if row["status"] == "skipped_existing")
    failed = sum(1 for row in rows if row["status"] == "failed")
    print(f"Done. downloaded={downloaded}, skipped_existing={skipped}, failed={failed}, report={report_path}")


if __name__ == "__main__":
    main()
