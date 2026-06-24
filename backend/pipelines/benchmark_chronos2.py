from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import pandas as pd
import psutil


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "backend" / "data" / "processed" / "nasa_station_data" / "3h_picked" / "dhaka.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs" / "tables" / "operational_forecast" / "sota_resource_benchmark.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark the local Apache-2.0 Chronos-2 checkpoint.")
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    from chronos import Chronos2Pipeline

    frame = pd.read_csv(args.input)
    frame["timestamp"] = pd.to_datetime(
        {"year": frame["YEAR"], "month": frame["MO"], "day": frame["DY"]}
    ) + pd.to_timedelta(frame["HR"], unit="h")
    frame = frame.tail(720).copy()
    frame["item_id"] = "dhaka"
    variables = ["T2M", "RH2M", "PRECTOTCORR", "WS10M"]

    load_started = time.perf_counter()
    pipeline = Chronos2Pipeline.from_pretrained("amazon/chronos-2", device_map=args.device)
    load_seconds = time.perf_counter() - load_started
    predict_started = time.perf_counter()
    output = pipeline.predict_df(
        frame[["item_id", "timestamp", *variables]],
        id_column="item_id",
        timestamp_column="timestamp",
        target=variables,
        prediction_length=32,
        quantile_levels=[0.05, 0.5, 0.95],
        freq="3h",
    )
    predict_seconds = time.perf_counter() - predict_started
    rss_mb = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
    result = {
        "candidate": "chronos-2",
        "checkpoint": "amazon/chronos-2",
        "device": args.device,
        "context_steps": 720,
        "forecast_steps": 32,
        "variables": variables,
        "output_rows": len(output),
        "load_seconds": load_seconds,
        "predict_seconds": predict_seconds,
        "rss_mb": rss_mb,
        "latency_gate_seconds": 5.0,
        "memory_gate_mb": 2048,
        "latency_gate_passed": predict_seconds < 5.0,
        "memory_gate_passed": rss_mb < 2048,
        "production_eligible": predict_seconds < 5.0 and rss_mb < 2048,
        "license": "Apache-2.0",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

