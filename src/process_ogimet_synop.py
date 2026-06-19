from __future__ import annotations

import argparse
import csv
import glob
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_GLOB = str(PROJECT_ROOT / "data" / "raw" / "ground_ogimet" / "*.txt")
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "processed" / "ogimet_synop"
DEFAULT_REPORT = PROJECT_ROOT / "outputs" / "tables" / "ogimet_synop_processing_report.csv"

OUTPUT_COLUMNS = ["YEAR", "MO", "DY", "HR", "T2M", "RH2M", "PRECTOTCORR", "WS10M"]

# Map OGIMET WMO block id -> BMD `station_id` slug (35-station study set).
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

HEADER_RE = re.compile(r"^\s*#\s*SYNOPS from (\d+),\s*(.+?)\s*\(Bangladesh\)")
START_RE = re.compile(r"^(\d{12})\s+AAXX\s+")
TOKEN_RE = re.compile(r"[^\s=]+")


def extract_pre_body(text: str) -> str:
    """Return text inside the first <pre>...</pre> block if present; otherwise the full string."""
    lower = text.lower()
    start = lower.find("<pre>")
    end = lower.find("</pre>")
    if start != -1 and end != -1 and end > start:
        return text[start + len("<pre>") : end]
    return text


def relative_temperature(token: str) -> float | None:
    """Decode 1snTTT or 2snTdTdTd (tenths °C)."""
    if len(token) != 5 or token[0] not in "12":
        return None
    sign = -1.0 if token[1] == "1" else 1.0
    try:
        tenths = int(token[2:5])
    except ValueError:
        return None
    return sign * tenths / 10.0


def magnus_rh_percent(t_c: float, td_c: float) -> float | None:
    """Relative humidity (%) from dry-bulb and dew point (°C), Sonntag approximations."""
    if math.isnan(t_c) or math.isnan(td_c):
        return None
    if td_c > t_c + 0.2:
        return None
    # Saturation vapor pressure over water (hPa)
    es = 6.112 * math.exp((17.67 * t_c) / (t_c + 243.5))
    e = 6.112 * math.exp((17.67 * td_c) / (td_c + 243.5))
    if es <= 0:
        return None
    rh = 100.0 * (e / es)
    return max(0.0, min(100.0, rh))


def wind_speed_ms(ff: int, iw: int) -> float:
    """WMO Code Table 4680 — wind speed from ff, given indicator i (last digit of YYGGiw in practice)."""
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


def parse_yyggiw_iw(yyggiw: str) -> int:
    if len(yyggiw) < 5:
        return 4
    last = int(yyggiw[-1])
    if 0 <= last <= 8:
        return last
    third = int(yyggiw[3]) if yyggiw[3].isdigit() else 4
    if 0 <= third <= 8:
        return third
    return 4


def parse_nddff(token: str) -> tuple[int, int, int] | None:
    t = token.rstrip("/")
    if len(t) != 5 or not t.isdigit():
        return None
    n, dd, ff = int(t[0]), int(t[1:3]), int(t[3:5])
    if n < 0 or n > 9:
        return None
    # WMO: dd = 00 calm, 99 variable, else 01–36 (direction in tens of degrees).
    if dd not in (0, 99) and not (1 <= dd <= 36):
        return None
    if ff < 0 or ff > 99:
        return None
    return n, dd, ff


def precip_mm_from_6_group(token: str) -> tuple[float | None, int | None]:
    """
    Group 6RRRt (5 chars): WMO Code 3590/3591 — RRR amount (tenths of mm for 001–988),
    t = duration code (table 3590). 990 = trace, 991–998 = 0.1–0.8 mm, 999 = not available.
    """
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


# Table 3590: duration associated with t_R (hours). Used to prefer 3-hour amounts when multiple 6-groups exist.
TR_HOURS_APPROX: dict[int, float] = {
    1: 6.0,
    2: 12.0,
    3: 18.0,
    4: 24.0,
    5: 1.0,
    6: 2.0,
    7: 3.0,
    8: 9.0,
    9: 15.0,
}
# Lower sort key = preferred when choosing among several 6RRRt groups (favor 3 h, then 1 h, …).
TR_SORT_KEY: dict[int, int] = {
    7: 0,
    5: 1,
    6: 2,
    1: 3,
    2: 4,
    3: 5,
    4: 6,
    8: 7,
    9: 8,
}


def best_precip_mm_from_6_groups(tokens: list[str], skip: set[str]) -> float | None:
    """
    Best 6RRRt amount (mm); prefers t_R=7 (3 h). Skips Nddff (and any other) tokens — wind groups
    like 63602 start with '6' but are not 6RRRt.
    """
    candidates: list[tuple[int, float]] = []
    for tok in tokens:
        if tok in skip:
            continue
        mm, tr = precip_mm_from_6_group(tok)
        if mm is None or tr is None:
            continue
        key = TR_SORT_KEY.get(tr, 50)
        candidates.append((key, mm))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def precipitation_mm(s1: list[str], tokens: list[str], nddff_tok: str | None) -> float | None:
    """
    WMO Code 1819 (first digit of iRixhVV): 3 = no precipitation; 4 = amount not available.
    Otherwise use 6RRRt groups anywhere in the bulletin (section 1 or 3).
    Returns None when amount is unknown or not reported (CSV left empty).
    """
    if len(s1) > 4 and s1[4] and s1[4][0].isdigit():
        ir = int(s1[4][0])
        if ir == 3:
            return 0.0
        if ir == 4:
            return None
    skip = {t for t in (nddff_tok,) if t}
    return best_precip_mm_from_6_groups(tokens, skip)


@dataclass
class BulletinState:
    lines: list[str] = field(default_factory=list)


def tokens_section1(tokens: list[str]) -> list[str]:
    """Regional data (often introduced by 333) must not be scanned for 1snTTT."""
    try:
        idx = tokens.index("333")
        return tokens[:idx]
    except ValueError:
        return tokens


def decode_synop_raw(
    raw: str,
    wmo: str,
    rows_by_wmo: dict[str, list[dict[str, Any]]],
    stats: dict[str, Any],
) -> None:
    """Decode one SYNOP bulletin prefixed with YYYYMMDDHHmm (OGIMET HTML or getsynop CSV)."""
    raw = raw.replace("NIL=", " NIL ")
    tokens = TOKEN_RE.findall(raw)
    if len(tokens) < 4 or tokens[1] != "AAXX":
        stats["parse_skipped"] += 1
        return
    if "NIL" in tokens:
        dt_tok = tokens[0]
        try:
            obs = datetime.strptime(dt_tok, "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
        except ValueError:
            stats["parse_skipped"] += 1
            return
        row = {
            "YEAR": obs.year,
            "MO": obs.month,
            "DY": obs.day,
            "HR": obs.hour,
            "T2M": math.nan,
            "RH2M": math.nan,
            "PRECTOTCORR": math.nan,
            "WS10M": math.nan,
        }
        rows_by_wmo[wmo].append(row)
        stats["nil_rows"] += 1
        return

    yyggiw = tokens[2]
    iw = parse_yyggiw_iw(yyggiw)
    s1 = tokens_section1(tokens)
    # Land SYNOP section 1 order: AAXX YYGGiw IIiii iRixhVV Nddff 1snTTT 2snTdTdTd ...
    # Do not scan for "any" 5-digit group: values like 10265 are 1snTTT (temp), not Nddff.
    nddff_tok = None
    nddff_idx: int | None = None
    if len(s1) > 5:
        candidate = s1[5]
        if parse_nddff(candidate):
            nddff_tok = candidate
            nddff_idx = 5
    t2m: float | None = None
    tdew: float | None = None
    scan_start = (nddff_idx + 1) if nddff_idx is not None else 4
    for tok in s1[scan_start : scan_start + 12]:
        if tok.startswith("1") and t2m is None:
            v = relative_temperature(tok)
            if v is not None:
                t2m = v
        elif tok.startswith("2") and tdew is None:
            v = relative_temperature(tok)
            if v is not None:
                tdew = v
    rh = magnus_rh_percent(t2m, tdew) if t2m is not None and tdew is not None else None

    ws_ms: float | None = None
    if nddff_tok:
        parsed = parse_nddff(nddff_tok)
        if parsed:
            _, _, ff = parsed
            ws_ms = wind_speed_ms(ff, iw)

    p_mm = precipitation_mm(s1, tokens, nddff_tok)
    precip = math.nan if p_mm is None else p_mm

    dt_tok = tokens[0]
    try:
        obs = datetime.strptime(dt_tok, "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
    except ValueError:
        stats["parse_skipped"] += 1
        return

    row = {
        "YEAR": obs.year,
        "MO": obs.month,
        "DY": obs.day,
        "HR": obs.hour,
        "T2M": t2m if t2m is not None else math.nan,
        "RH2M": rh if rh is not None else math.nan,
        "PRECTOTCORR": precip,
        "WS10M": ws_ms if ws_ms is not None else math.nan,
    }
    rows_by_wmo[wmo].append(row)
    stats["decoded_rows"] += 1


def flush_bulletin(
    state: BulletinState,
    wmo: str,
    rows_by_wmo: dict[str, list[dict[str, Any]]],
    stats: dict[str, Any],
) -> None:
    if not state.lines or not wmo:
        return
    decode_synop_raw(" ".join(state.lines), wmo, rows_by_wmo, stats)


def is_getsynop_csv(path: Path) -> bool:
    sample = path.read_text(encoding="utf-8-sig", errors="replace")[:500].upper()
    return "PARTE" in sample and ("ESTACION" in sample or "WMOIND" in sample)


def parse_getsynop_csv(path: Path) -> dict[str, list[dict[str, Any]]]:
    """OGIMET getsynop CSV: ESTACION, ANO, MES, DIA, HORA, MINUTO, PARTE."""
    rows_by_wmo: dict[str, list[dict[str, Any]]] = defaultdict(list)
    stats = {"nil_rows": 0, "decoded_rows": 0, "parse_skipped": 0}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            norm = {((k or "").strip().upper()): ((v or "").strip()) for k, v in row.items()}
            wmo_raw = norm.get("ESTACION") or norm.get("WMOIND") or ""
            parte = norm.get("PARTE") or norm.get("REPORT") or ""
            if not wmo_raw or not parte:
                stats["parse_skipped"] += 1
                continue
            try:
                wmo = str(int(wmo_raw))
                y = int(norm["ANO"])
                mo = int(norm["MES"])
                d = int(norm["DIA"])
                h = int(norm["HORA"])
                mi = int(norm.get("MINUTO") or "0")
            except (KeyError, ValueError):
                stats["parse_skipped"] += 1
                continue
            prefix = f"{y}{mo:02d}{d:02d}{h:02d}{mi:02d}"
            decode_synop_raw(f"{prefix} {parte}", wmo, rows_by_wmo, stats)
    rows_by_wmo["_stats"] = [stats]  # type: ignore[assignment]
    return rows_by_wmo


def parse_ogimet_file(path: Path) -> dict[str, list[dict[str, Any]]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    body = extract_pre_body(text)
    rows_by_wmo: dict[str, list[dict[str, Any]]] = defaultdict(list)
    current_wmo = ""
    bulletin: BulletinState | None = None
    stats = {"nil_rows": 0, "decoded_rows": 0, "parse_skipped": 0}

    for line in body.splitlines():
        header = HEADER_RE.match(line)
        if header:
            if bulletin:
                flush_bulletin(bulletin, current_wmo, rows_by_wmo, stats)
            bulletin = None
            current_wmo = header.group(1)
            continue

        start = START_RE.match(line)
        if start:
            if bulletin:
                flush_bulletin(bulletin, current_wmo, rows_by_wmo, stats)
            rest = line[start.end() :].strip()
            bulletin = BulletinState(lines=[start.group(1), "AAXX", rest])
            continue

        if bulletin and line.strip() and not line.lstrip().startswith("#"):
            stripped = line.strip()
            if stripped.startswith("="):
                continue
            continuation = stripped
            if continuation.endswith("="):
                continuation = continuation.rstrip("=").strip()
            if bulletin.lines:
                bulletin.lines[-1] = f"{bulletin.lines[-1]} {continuation}"
            continue

    if bulletin:
        flush_bulletin(bulletin, current_wmo, rows_by_wmo, stats)

    rows_by_wmo["_stats"] = [stats]  # type: ignore[assignment]
    return rows_by_wmo


def dataframe_from_rows(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["YEAR", "MO", "DY", "HR"], keep="last")
    df = df.sort_values(["YEAR", "MO", "DY", "HR"]).reset_index(drop=True)
    return df[OUTPUT_COLUMNS]


def write_station_csv(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, float_format="%.6g", na_rep="")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Convert OGIMET Bangladesh SYNOP text dumps into CSV files "
            f"with columns {', '.join(OUTPUT_COLUMNS)}. "
            "Uses OGIMET's 12-digit UTC stamp for time; decodes FM-12 land groups where present. "
            "PRECTOTCORR is only filled when a 6RRRt_R group is parsed (often missing in SYNOP)."
        )
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        help="Raw .txt files (default: glob data/raw/ground_ogimet/*.txt).",
    )
    parser.add_argument("--glob-pattern", default=DEFAULT_RAW_GLOB, help="Used when no inputs are passed.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--no-by-wmo",
        action="store_true",
        help="Do not write by_wmo/<wmo>.csv files.",
    )
    parser.add_argument(
        "--no-by-station",
        action="store_true",
        help="Do not write by_station/<station_id>.csv files.",
    )
    args = parser.parse_args()

    output_root = args.output_root if args.output_root.is_absolute() else PROJECT_ROOT / args.output_root
    report_path = args.report if args.report.is_absolute() else PROJECT_ROOT / args.report

    if args.inputs:
        files = [p if p.is_absolute() else PROJECT_ROOT / p for p in args.inputs]
    else:
        files = sorted(Path(p) for p in glob.glob(args.glob_pattern))
        if not files:
            files = sorted(PROJECT_ROOT.glob("data/raw/ground_ogimet/*.txt"))
            files += sorted(PROJECT_ROOT.glob("data/raw/ground_ogimet/*.csv"))

    by_wmo = not args.no_by_wmo
    by_station = not args.no_by_station

    merged_by_wmo: dict[str, list[dict[str, Any]]] = defaultdict(list)
    report_rows: list[dict[str, Any]] = []

    for path in files:
        if not path.exists():
            print(f"Skip missing: {path}")
            continue
        if path.suffix.lower() == ".csv" or is_getsynop_csv(path):
            parsed = parse_getsynop_csv(path)
        else:
            parsed = parse_ogimet_file(path)
        stats_list = parsed.pop("_stats", [{}])
        stats = stats_list[0] if stats_list else {}
        for wmo, rows in parsed.items():
            merged_by_wmo[wmo].extend(rows)
        report_rows.append(
            {
                "source_file": str(path.relative_to(PROJECT_ROOT))
                if path.resolve().is_relative_to(PROJECT_ROOT.resolve())
                else str(path),
                "wmo_stations": len(parsed),
                "decoded_rows": stats.get("decoded_rows", 0),
                "nil_rows": stats.get("nil_rows", 0),
                "parse_skipped": stats.get("parse_skipped", 0),
            }
        )

    if by_wmo:
        wmo_dir = output_root / "by_wmo"
        for wmo, rows in sorted(merged_by_wmo.items()):
            df = dataframe_from_rows(rows)
            write_station_csv(wmo_dir / f"{wmo}.csv", df)
            print(f"Wrote {wmo_dir / (wmo + '.csv')} ({len(df)} rows)")

    if by_station:
        station_dir = output_root / "by_station"
        by_station_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for wmo, rows in merged_by_wmo.items():
            sid = WMO_TO_STATION_ID.get(wmo)
            if sid:
                by_station_rows[sid].extend(rows)
        for sid, rows in sorted(by_station_rows.items()):
            df = dataframe_from_rows(rows)
            write_station_csv(station_dir / f"{sid}.csv", df)
            print(f"Wrote {station_dir / (sid + '.csv')} ({len(df)} rows)")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "source_file",
                "wmo_stations",
                "decoded_rows",
                "nil_rows",
                "parse_skipped",
            ],
        )
        writer.writeheader()
        writer.writerows(report_rows)
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
