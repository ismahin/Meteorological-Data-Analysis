from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BMD_DIR = PROJECT_ROOT / "data" / "processed" / "bmd_stations_3hourly"
NASA_ROOT = PROJECT_ROOT / "data" / "processed" / "nasa_station_data"
TABLE_DIR = PROJECT_ROOT / "outputs" / "tables" / "bmd_nasa_comparison"
REPORT_DIR = PROJECT_ROOT / "outputs" / "reports"

KEY_COLUMNS = ["YEAR", "MO", "DY", "HR"]
VARIABLES = ["T2M", "RH2M", "PRECTOTCORR", "WS10M"]
VAR_LABELS = {
    "T2M": "Temperature at 2 m",
    "RH2M": "Relative humidity at 2 m",
    "PRECTOTCORR": "Precipitation",
    "WS10M": "Wind speed at 10 m",
}
VAR_UNITS = {
    "T2M": "deg C",
    "RH2M": "%",
    "PRECTOTCORR": "mm / 3h",
    "WS10M": "m/s",
}
VAR_AGG = {
    "T2M": "mean",
    "RH2M": "mean",
    "PRECTOTCORR": "sum",
    "WS10M": "mean",
}
VARIANTS = {
    "3h_average": NASA_ROOT / "3h_average",
    "3h_picked": NASA_ROOT / "3h_picked",
}
RAIN_THRESHOLDS = [0.1, 5.0, 10.0, 25.0]


def season_name(month: int) -> str:
    if month in {12, 1, 2}:
        return "Winter_DJF"
    if month in {3, 4, 5}:
        return "PreMonsoon_MAM"
    if month in {6, 7, 8, 9}:
        return "Monsoon_JJAS"
    return "PostMonsoon_ON"


def read_pair(bmd_path: Path, nasa_path: Path) -> pd.DataFrame:
    bmd = pd.read_csv(bmd_path)
    nasa = pd.read_csv(nasa_path)
    merged = bmd.merge(nasa, on=KEY_COLUMNS, suffixes=("_bmd", "_nasa"), validate="one_to_one")
    merged.insert(0, "station_id", bmd_path.stem)
    merged["date"] = pd.to_datetime(
        {
            "year": merged["YEAR"],
            "month": merged["MO"],
            "day": merged["DY"],
        }
    )
    merged["month"] = merged["MO"].astype(int)
    merged["season"] = merged["month"].map(season_name)
    return merged


def load_variant(variant_dir: Path) -> pd.DataFrame:
    frames = []
    for bmd_path in sorted(BMD_DIR.glob("*.csv")):
        nasa_path = variant_dir / bmd_path.name
        if not nasa_path.exists():
            raise FileNotFoundError(nasa_path)
        frames.append(read_pair(bmd_path, nasa_path))
    return pd.concat(frames, ignore_index=True)


def safe_corr(obs: pd.Series, sim: pd.Series) -> float:
    if len(obs) < 2 or obs.std(ddof=0) == 0 or sim.std(ddof=0) == 0:
        return math.nan
    return float(np.corrcoef(obs, sim)[0, 1])


def metrics_from_arrays(obs: pd.Series, sim: pd.Series) -> dict[str, Any]:
    paired = pd.concat([obs, sim], axis=1).dropna()
    paired.columns = ["obs", "sim"]
    if paired.empty:
        return {
            "n": 0,
            "bmd_mean": math.nan,
            "nasa_mean": math.nan,
            "bias": math.nan,
            "mae": math.nan,
            "rmse": math.nan,
            "ubrmse": math.nan,
            "pearson_r": math.nan,
            "r2": math.nan,
            "nse": math.nan,
            "kge": math.nan,
            "pbias_percent": math.nan,
            "std_ratio": math.nan,
        }

    obs_values = paired["obs"]
    sim_values = paired["sim"]
    diff = sim_values - obs_values
    obs_mean = obs_values.mean()
    sim_mean = sim_values.mean()
    obs_std = obs_values.std(ddof=0)
    sim_std = sim_values.std(ddof=0)
    corr = safe_corr(obs_values, sim_values)
    rmse = float(np.sqrt(np.mean(diff**2)))
    centered = (sim_values - sim_mean) - (obs_values - obs_mean)
    nse_den = float(np.sum((obs_values - obs_mean) ** 2))
    obs_sum = float(obs_values.sum())
    alpha = sim_std / obs_std if obs_std != 0 else math.nan
    beta = sim_mean / obs_mean if obs_mean != 0 else math.nan
    kge = (
        1 - math.sqrt((corr - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2)
        if not any(math.isnan(value) for value in [corr, alpha, beta])
        else math.nan
    )
    return {
        "n": int(len(paired)),
        "bmd_mean": float(obs_mean),
        "nasa_mean": float(sim_mean),
        "bias": float(diff.mean()),
        "mae": float(diff.abs().mean()),
        "rmse": rmse,
        "ubrmse": float(np.sqrt(np.mean(centered**2))),
        "pearson_r": corr,
        "r2": float(corr**2) if not math.isnan(corr) else math.nan,
        "nse": float(1 - np.sum(diff**2) / nse_den) if nse_den != 0 else math.nan,
        "kge": float(kge),
        "pbias_percent": float(100 * diff.sum() / obs_sum) if obs_sum != 0 else math.nan,
        "std_ratio": float(alpha),
    }


def metric_rows(df: pd.DataFrame, group_columns: list[str], scale: str) -> pd.DataFrame:
    rows = []
    groups = [((), df)] if not group_columns else df.groupby(group_columns, dropna=False)
    for group_key, group in groups:
        if not isinstance(group_key, tuple):
            group_key = (group_key,)
        base = dict(zip(group_columns, group_key))
        for variable in VARIABLES:
            row = {
                **base,
                "scale": scale,
                "variable": variable,
                "label": VAR_LABELS[variable],
                "unit": VAR_UNITS[variable],
            }
            row.update(metrics_from_arrays(group[f"{variable}_bmd"], group[f"{variable}_nasa"]))
            rows.append(row)
    return pd.DataFrame(rows)


def aggregate_daily(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    grouped = df.groupby(["station_id", "date"], as_index=False)
    for (station_id, date), group in grouped:
        row: dict[str, Any] = {"station_id": station_id, "date": date}
        row["YEAR"] = int(group["YEAR"].iloc[0])
        row["MO"] = int(group["MO"].iloc[0])
        row["season"] = group["season"].iloc[0]
        for variable, operation in VAR_AGG.items():
            for source in ["bmd", "nasa"]:
                column = f"{variable}_{source}"
                row[column] = group[column].sum() if operation == "sum" else group[column].mean()
        rows.append(row)
    return pd.DataFrame(rows)


def aggregate_monthly(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    grouped = df.groupby(["station_id", "YEAR", "MO"], as_index=False)
    for (station_id, year, month), group in grouped:
        row: dict[str, Any] = {"station_id": station_id, "YEAR": year, "MO": month}
        row["season"] = season_name(int(month))
        for variable, operation in VAR_AGG.items():
            for source in ["bmd", "nasa"]:
                column = f"{variable}_{source}"
                row[column] = group[column].sum() if operation == "sum" else group[column].mean()
        rows.append(row)
    return pd.DataFrame(rows)


def precipitation_events(df: pd.DataFrame, group_columns: list[str]) -> pd.DataFrame:
    rows = []
    groups = [((), df)] if not group_columns else df.groupby(group_columns, dropna=False)
    for group_key, group in groups:
        if not isinstance(group_key, tuple):
            group_key = (group_key,)
        base = dict(zip(group_columns, group_key))
        for threshold in RAIN_THRESHOLDS:
            obs_wet = group["PRECTOTCORR_bmd"] >= threshold
            sim_wet = group["PRECTOTCORR_nasa"] >= threshold
            hits = int((obs_wet & sim_wet).sum())
            misses = int((obs_wet & ~sim_wet).sum())
            false_alarms = int((~obs_wet & sim_wet).sum())
            correct_negatives = int((~obs_wet & ~sim_wet).sum())
            row = {
                **base,
                "threshold_mm": threshold,
                "hits": hits,
                "misses": misses,
                "false_alarms": false_alarms,
                "correct_negatives": correct_negatives,
                "pod": hits / (hits + misses) if hits + misses else math.nan,
                "far": false_alarms / (hits + false_alarms) if hits + false_alarms else math.nan,
                "csi": hits / (hits + misses + false_alarms)
                if hits + misses + false_alarms
                else math.nan,
                "frequency_bias": (hits + false_alarms) / (hits + misses)
                if hits + misses
                else math.nan,
                "accuracy": (hits + correct_negatives)
                / (hits + misses + false_alarms + correct_negatives),
            }
            rows.append(row)
    return pd.DataFrame(rows)


def monthly_climatology_bias(monthly: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for month, group in monthly.groupby("MO"):
        for variable in VARIABLES:
            row = {
                "MO": int(month),
                "variable": variable,
                "label": VAR_LABELS[variable],
                "unit": VAR_UNITS[variable],
                "bmd_mean": group[f"{variable}_bmd"].mean(),
                "nasa_mean": group[f"{variable}_nasa"].mean(),
                "bias": (group[f"{variable}_nasa"] - group[f"{variable}_bmd"]).mean(),
            }
            rows.append(row)
    return pd.DataFrame(rows)


def round_for_report(df: pd.DataFrame, decimals: int = 3) -> pd.DataFrame:
    result = df.copy()
    for column in result.select_dtypes(include=[np.number]).columns:
        result[column] = result[column].round(decimals)
    return result


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int | None = None) -> str:
    table = df[columns].copy()
    if max_rows is not None:
        table = table.head(max_rows)
    return round_for_report(table).to_markdown(index=False)


def write_variant_report(
    variant: str,
    overall_3h: pd.DataFrame,
    overall_daily: pd.DataFrame,
    station_3h: pd.DataFrame,
    seasonal: pd.DataFrame,
    event_overall: pd.DataFrame,
    monthly_bias: pd.DataFrame,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    overall_index = overall_3h.set_index("variable")
    temp = overall_index.loc["T2M"]
    rh = overall_index.loc["RH2M"]
    rain = overall_index.loc["PRECTOTCORR"]
    wind = overall_index.loc["WS10M"]
    station_rank = station_3h.assign(abs_bias=lambda d: d["bias"].abs())
    worst_rmse = (
        station_rank.sort_values(["variable", "rmse"], ascending=[True, False])
        .groupby("variable")
        .head(3)
        [["variable", "station_id", "bias", "mae", "rmse", "pearson_r", "pbias_percent"]]
    )
    best_corr = (
        station_rank.sort_values(["variable", "pearson_r"], ascending=[True, False])
        .groupby("variable")
        .head(3)
        [["variable", "station_id", "bias", "rmse", "pearson_r"]]
    )
    seasonal_bias = seasonal[["season", "variable", "bias", "rmse", "pearson_r", "pbias_percent"]]

    text = f"""# BMD vs NASA POWER Comparison Report: `{variant}`

## Research Basis

This report treats BMD station observations as the reference and NASA POWER as the gridded estimate at the station coordinate. The metric set follows common meteorological and hydroclimate validation practice:

- NASA POWER's own meteorology assessment uses linear regression, Pearson correlation, mean bias error, MAE, and RMSE for station comparisons.
- NASA POWER hourly data are hourly-average products; precipitation is provided as `mm/hour`, so this project sums hourly `PRECTOTCORR` into 3-hour totals before comparing with BMD.
- Precipitation validation should include both amount metrics and event-detection metrics because rain occurrence can be wrong even when totals look acceptable.
- NSE and KGE are included because hydroclimate studies often use them to evaluate timing, variability, and bias together.
- Seasonal and monthly summaries are included because Bangladesh monsoon behavior can dominate annual statistics.

References are listed at the end of this report.

## Dataset Alignment

- BMD folder: `data/processed/bmd_stations_3hourly/`
- NASA folder: `data/processed/nasa_station_data/{variant}/`
- Stations: 35
- Time step: 3-hourly
- Period: 2021-01-01 to 2024-12-31
- Rows per station: 11,688
- Columns: `YEAR, MO, DY, HR, T2M, RH2M, PRECTOTCORR, WS10M`
- Rainfall unit treatment: NASA hourly precipitation was summed to 3-hour totals.

## Key Findings

- Temperature agreement is strong: `r={temp["pearson_r"]:.3f}`, `RMSE={temp["rmse"]:.3f} deg C`, and mean bias is `{temp["bias"]:.3f} deg C`.
- Relative humidity agreement is moderate: `r={rh["pearson_r"]:.3f}`, `RMSE={rh["rmse"]:.3f}%`, and mean bias is `{rh["bias"]:.3f}%`.
- Wind speed has a positive NASA bias: mean BMD is `{wind["bmd_mean"]:.3f} m/s`, mean NASA is `{wind["nasa_mean"]:.3f} m/s`, and bias is `{wind["bias"]:.3f} m/s`.
- Precipitation is the largest problem: NASA mean 3-hour precipitation is `{rain["nasa_mean"]:.3f} mm` versus BMD `{rain["bmd_mean"]:.3f} mm`, with percent bias `{rain["pbias_percent"]:.1f}%`.
- Because precipitation is strongly intermittent, use the event-detection table together with RMSE/bias before drawing rainfall conclusions.

## Overall 3-Hourly Metrics

{markdown_table(overall_3h, ["variable", "unit", "bmd_mean", "nasa_mean", "bias", "mae", "rmse", "pearson_r", "nse", "kge", "pbias_percent"])}

## Overall Daily Metrics

Daily aggregation uses means for `T2M`, `RH2M`, and `WS10M`, and sums for `PRECTOTCORR`.

{markdown_table(overall_daily, ["variable", "unit", "bmd_mean", "nasa_mean", "bias", "mae", "rmse", "pearson_r", "nse", "kge", "pbias_percent"])}

## Precipitation Event Detection

`POD` is probability of detection, `FAR` is false alarm ratio, `CSI` is critical success index, and frequency bias above 1 means NASA detects too many events.

{markdown_table(event_overall, ["threshold_mm", "hits", "misses", "false_alarms", "pod", "far", "csi", "frequency_bias", "accuracy"])}

## Seasonal Signal

{markdown_table(seasonal_bias, ["season", "variable", "bias", "rmse", "pearson_r", "pbias_percent"], max_rows=20)}

## Monthly Mean Bias

{markdown_table(monthly_bias, ["MO", "variable", "bias"], max_rows=48)}

## Stations With Largest 3-Hourly RMSE

{markdown_table(worst_rmse, ["variable", "station_id", "bias", "mae", "rmse", "pearson_r", "pbias_percent"], max_rows=12)}

## Stations With Highest 3-Hourly Correlation

{markdown_table(best_corr, ["variable", "station_id", "bias", "rmse", "pearson_r"], max_rows=12)}

## Interpretation Priorities

1. Use `bias` and `pbias_percent` to identify systematic over/underestimation.
2. Use `MAE` and `RMSE` to judge typical and large-error behavior in physical units.
3. Use `pearson_r`, `NSE`, and `KGE` to judge whether NASA captures timing and variability, not only mean conditions.
4. For precipitation, prioritize event metrics and seasonal/monthly totals; precipitation is intermittent and strongly skewed.
5. Compare this report with the other NASA variant. If the averaged variant improves RMSE for temperature, humidity, and wind without harming correlation, it is generally the better comparison dataset. For precipitation, both variants use the same 3-hour sum.

## References

- NASA POWER Hourly API: https://power.larc.nasa.gov/docs/services/api/temporal/hourly/
- NASA POWER Meteorology Assessment: https://power.larc.nasa.gov/docs/methodology/meteorology/assessment/
- NOAA/NASA precipitation validation methods: https://precip-val.umd.edu/validation-methods
- HESS discussion of NSE and KGE: https://hess.copernicus.org/articles/23/4323/2019/hess-23-4323-2019.html
- Taylor diagram model evaluation background: https://openair-project.github.io/book/sections/model-evaluation/taylor-diagram.html
"""
    output_path.write_text(text, encoding="utf-8")


def analyze_variant(variant: str, variant_dir: Path) -> None:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    data = load_variant(variant_dir)
    daily = aggregate_daily(data)
    monthly = aggregate_monthly(data)

    overall_3h = metric_rows(data, [], "3hour")
    station_3h = metric_rows(data, ["station_id"], "3hour")
    seasonal = metric_rows(data, ["season"], "3hour")
    overall_daily = metric_rows(daily, [], "daily")
    station_daily = metric_rows(daily, ["station_id"], "daily")
    event_overall = precipitation_events(data, [])
    event_station = precipitation_events(data, ["station_id"])
    monthly_bias = monthly_climatology_bias(monthly)

    outputs = {
        "overall_3hour_metrics": overall_3h,
        "station_3hour_metrics": station_3h,
        "seasonal_3hour_metrics": seasonal,
        "overall_daily_metrics": overall_daily,
        "station_daily_metrics": station_daily,
        "precip_event_overall": event_overall,
        "precip_event_station": event_station,
        "monthly_climatology_bias": monthly_bias,
    }
    for name, frame in outputs.items():
        frame.to_csv(TABLE_DIR / f"{variant}_{name}.csv", index=False)

    write_variant_report(
        variant=variant,
        overall_3h=overall_3h,
        overall_daily=overall_daily,
        station_3h=station_3h,
        seasonal=seasonal,
        event_overall=event_overall,
        monthly_bias=monthly_bias,
        output_path=REPORT_DIR / f"bmd_nasa_comparison_{variant}.md",
    )
    print(f"Wrote analysis outputs for {variant}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze BMD station observations against processed NASA POWER variants."
    )
    parser.add_argument("--variant", choices=sorted(VARIANTS), help="Optional single variant.")
    args = parser.parse_args()

    variants = {args.variant: VARIANTS[args.variant]} if args.variant else VARIANTS
    for variant, variant_dir in variants.items():
        analyze_variant(variant, variant_dir)
    print(f"Reports saved in {REPORT_DIR}")
    print(f"Tables saved in {TABLE_DIR}")


if __name__ == "__main__":
    main()
