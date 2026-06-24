from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.bias_correction_core import VARIABLES, load_station_timeseries, load_stations  # noqa: E402
from pipelines.train_operational_forecast_model import (  # noqa: E402
    DEFAULT_BMD_DIR,
    DEFAULT_NASA_DIR,
    DEFAULT_STATIONS_JSON,
    HOLDOUT_STATIONS,
    HORIZONS,
    horizon_bucket,
    metric_summary,
    rain_metrics,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "outputs" / "tables" / "operational_forecast" / "chronos2_accuracy_metrics.csv"
DEFAULT_DETAILS = PROJECT_ROOT / "outputs" / "tables" / "operational_forecast" / "chronos2_accuracy_predictions.csv"


def residual_offsets(frames: dict[str, pd.DataFrame]) -> dict[str, dict[tuple[int, int], float]]:
    tables: dict[str, list[pd.DataFrame]] = {variable: [] for variable in VARIABLES}
    for station_id, frame in frames.items():
        if station_id in HOLDOUT_STATIONS:
            continue
        train = frame[frame["timestamp"].dt.year <= 2022]
        for variable in VARIABLES:
            values = train[["MO", "HR", f"{variable}_bmd", f"{variable}_nasa"]].copy()
            values["residual"] = values[f"{variable}_bmd"] - values[f"{variable}_nasa"]
            tables[variable].append(values[["MO", "HR", "residual"]])
    return {
        variable: pd.concat(parts).groupby(["MO", "HR"])["residual"].median().to_dict()
        for variable, parts in tables.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Chronos-2 on unseen BMD stations in 2024.")
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    parser.add_argument("--origin-stride", type=int, default=64)
    parser.add_argument("--context-steps", type=int, default=720)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--details", type=Path, default=DEFAULT_DETAILS)
    args = parser.parse_args()

    from chronos import Chronos2Pipeline

    stations = load_stations(DEFAULT_STATIONS_JSON)
    frames = load_station_timeseries(stations, DEFAULT_BMD_DIR, DEFAULT_NASA_DIR)
    holdout_frames = {key: value.sort_values("timestamp").reset_index(drop=True) for key, value in frames.items() if key in HOLDOUT_STATIONS}
    offsets = residual_offsets(frames)
    pipeline = Chronos2Pipeline.from_pretrained("amazon/chronos-2", device_map=args.device)
    reference = next(iter(holdout_frames.values()))
    valid_origins = [
        index
        for index in range(args.context_steps - 1, len(reference) - 32, args.origin_stride)
        if reference.loc[index + 1, "timestamp"].year == 2024
    ]
    rows: list[dict[str, object]] = []
    started = time.perf_counter()
    for count, origin_index in enumerate(valid_origins, start=1):
        contexts = []
        for station_id, frame in holdout_frames.items():
            context = frame.iloc[origin_index - args.context_steps + 1 : origin_index + 1].copy()
            context["item_id"] = station_id
            contexts.append(context[["item_id", "timestamp", *[f"{v}_nasa" for v in VARIABLES]]].rename(columns={f"{v}_nasa": v for v in VARIABLES}))
        context_frame = pd.concat(contexts, ignore_index=True)
        forecast = pipeline.predict_df(
            context_frame,
            id_column="item_id",
            timestamp_column="timestamp",
            target=VARIABLES,
            prediction_length=32,
            quantile_levels=[0.05, 0.5, 0.95],
            freq="3h",
        )
        lookup = {
            (row.item_id, pd.Timestamp(row.timestamp), row.target_name): row
            for row in forecast.itertuples(index=False)
        }
        for station_id, frame in holdout_frames.items():
            for horizon_steps in [value for value in HORIZONS if value > 0]:
                target_row = frame.iloc[origin_index + horizon_steps]
                timestamp = pd.Timestamp(target_row["timestamp"])
                for variable in VARIABLES:
                    result = lookup[(station_id, timestamp, variable)]
                    offset = offsets[variable].get((timestamp.month, timestamp.hour), 0.0)
                    predicted = float(result.predictions) + float(offset)
                    baseline_persistence = float(frame.iloc[origin_index][f"{variable}_nasa"])
                    baseline_seasonal = float(frame.iloc[origin_index - 8][f"{variable}_nasa"])
                    if variable == "RH2M":
                        predicted = float(np.clip(predicted, 0, 100))
                    elif variable in {"PRECTOTCORR", "WS10M"}:
                        predicted = max(0.0, predicted)
                    rows.append(
                        {
                            "station_id": station_id,
                            "timestamp": timestamp,
                            "variable": variable,
                            "horizon_steps": horizon_steps,
                            "horizon_bucket": horizon_bucket(horizon_steps),
                            "observed": float(target_row[f"{variable}_bmd"]),
                            "predicted": predicted,
                            "baseline_persistence": baseline_persistence,
                            "baseline_seasonal": baseline_seasonal,
                        }
                    )
        print(f"[{count}/{len(valid_origins)}] {reference.loc[origin_index, 'timestamp']}")

    predictions = pd.DataFrame(rows).dropna(subset=["observed", "predicted"])
    metrics: list[dict[str, object]] = []
    for variable in VARIABLES:
        for bucket in sorted(predictions["horizon_bucket"].dropna().unique()):
            subset = predictions[(predictions["variable"] == variable) & (predictions["horizon_bucket"] == bucket)]
            observed = subset["observed"].to_numpy(dtype=float)
            chronos = subset["predicted"].to_numpy(dtype=float)
            candidates = {
                "chronos-2_plus_month_hour_bias": chronos,
                "nasa_persistence": subset["baseline_persistence"].to_numpy(dtype=float),
                "nasa_daily_seasonal": subset["baseline_seasonal"].to_numpy(dtype=float),
            }
            for candidate, values in candidates.items():
                row = {
                    "split": "spatial_temporal_test_2024",
                    "variable": variable,
                    "horizon_bucket": bucket,
                    "candidate": candidate,
                    **metric_summary(observed, values),
                }
                if variable == "PRECTOTCORR":
                    row.update(rain_metrics(observed, values))
                metrics.append(row)
    metrics_frame = pd.DataFrame(metrics)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    metrics_frame.to_csv(args.output, index=False)
    predictions.to_csv(args.details, index=False)
    print(metrics_frame.round(4).to_string(index=False))
    print(json.dumps({"elapsed_seconds": time.perf_counter() - started, "origins": len(valid_origins), "rows": len(predictions)}, indent=2))


if __name__ == "__main__":
    main()

