from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.bias_correction_core import (  # noqa: E402
    DEFAULT_BMD_DIR,
    DEFAULT_NASA_DIR,
    DEFAULT_STATIONS_JSON,
    RAIN_THRESHOLD_MM,
    VARIABLES,
    load_station_timeseries,
    load_stations,
)
from app.operational_forecast import (  # noqa: E402
    FEATURE_COLUMNS,
    FORECAST_VERSION,
    HORIZON_BUCKETS,
    LAG_STEPS,
    ROLLING_WINDOWS,
    horizon_bucket,
)


DEFAULT_MODEL_DIR = BACKEND_ROOT / "models" / "operational_forecast"
DEFAULT_TABLE_DIR = PROJECT_ROOT / "outputs" / "tables" / "operational_forecast"
DEFAULT_REPORT = PROJECT_ROOT / "outputs" / "reports" / "operational_forecast_validation.md"
DEFAULT_SOTA_BENCHMARK = DEFAULT_TABLE_DIR / "sota_resource_benchmark.json"
DEFAULT_CHRONOS_ACCURACY = DEFAULT_TABLE_DIR / "chronos2_accuracy_metrics.csv"
HOLDOUT_STATIONS = {"dhaka", "rangpur", "rajshahi", "sylhet", "khulna", "cox_s_bazar", "teknaf"}
HORIZONS = (0, 1, 2, 4, 8, 10, 12, 16, 18, 24, 26, 32)
INTERVAL_SAFETY_FACTORS = {"WS10M": 1.25}
BIAS_TOLERANCE_BY_VARIABLE = {
    "T2M": 0.5,
    "RH2M": 2.0,
    "PRECTOTCORR": 1.0,
    "WS10M": 0.2,
}


def data_source_label(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def metric_summary(observed: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    valid = np.isfinite(observed) & np.isfinite(predicted)
    observed = observed[valid]
    predicted = predicted[valid]
    if not len(observed):
        return {"n": 0, "bias": math.nan, "mae": math.nan, "rmse": math.nan, "pearson_r": math.nan}
    error = predicted - observed
    correlation = (
        float(np.corrcoef(observed, predicted)[0, 1])
        if len(observed) > 1 and np.std(observed) > 0 and np.std(predicted) > 0
        else math.nan
    )
    return {
        "n": int(len(observed)),
        "bias": float(np.mean(error)),
        "mae": float(mean_absolute_error(observed, predicted)),
        "rmse": float(mean_squared_error(observed, predicted) ** 0.5),
        "pearson_r": correlation,
    }


def rain_metrics(observed: np.ndarray, predicted: np.ndarray, probability: np.ndarray | None = None) -> dict[str, float]:
    valid = np.isfinite(observed) & np.isfinite(predicted)
    observed = observed[valid]
    predicted = predicted[valid]
    probability = probability[valid] if probability is not None else (predicted >= RAIN_THRESHOLD_MM).astype(float)
    wet = observed >= RAIN_THRESHOLD_MM
    predicted_wet = predicted >= RAIN_THRESHOLD_MM
    hits = int(np.sum(wet & predicted_wet))
    misses = int(np.sum(wet & ~predicted_wet))
    false_alarms = int(np.sum(~wet & predicted_wet))
    wet_pairs = wet & predicted_wet
    return {
        "brier": float(np.mean((probability - wet.astype(float)) ** 2)) if len(observed) else math.nan,
        "pod": hits / (hits + misses) if hits + misses else math.nan,
        "far": false_alarms / (hits + false_alarms) if hits + false_alarms else math.nan,
        "csi": hits / (hits + misses + false_alarms) if hits + misses + false_alarms else math.nan,
        "wet_amount_rmse": float(mean_squared_error(observed[wet_pairs], predicted[wet_pairs]) ** 0.5)
        if np.any(wet_pairs)
        else math.nan,
    }


def _time_features(timestamp: pd.Timestamp, prefix: str) -> dict[str, float]:
    month_angle = 2 * np.pi * timestamp.month / 12
    hour_angle = 2 * np.pi * timestamp.hour / 24
    month = timestamp.month
    season = 0 if month in {12, 1, 2} else 1 if month in {3, 4, 5} else 2 if month in {6, 7, 8, 9} else 3
    return {
        f"{prefix}_month": float(month),
        f"{prefix}_hour": float(timestamp.hour),
        f"{prefix}_season": float(season),
        f"{prefix}_sin_month": float(np.sin(month_angle)),
        f"{prefix}_cos_month": float(np.cos(month_angle)),
        f"{prefix}_sin_hour": float(np.sin(hour_angle)),
        f"{prefix}_cos_hour": float(np.cos(hour_angle)),
    }


def build_dataset(stations: list[Any], frames: dict[str, pd.DataFrame], origin_stride: int) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    max_lag = max(LAG_STEPS)
    max_horizon = max(HORIZONS)
    for station in stations:
        frame = frames[station.station_id].sort_values("timestamp").reset_index(drop=True)
        nasa = frame[[f"{variable}_nasa" for variable in VARIABLES]].to_numpy(dtype=float)
        bmd = frame[[f"{variable}_bmd" for variable in VARIABLES]].to_numpy(dtype=float)
        timestamps = pd.DatetimeIndex(frame["timestamp"])
        rolling: dict[tuple[int, int, str], np.ndarray] = {}
        for variable_index in range(len(VARIABLES)):
            series = pd.Series(nasa[:, variable_index])
            for window in ROLLING_WINDOWS:
                rolling[(variable_index, window, "mean")] = series.rolling(window, min_periods=1).mean().to_numpy()
                rolling[(variable_index, window, "std")] = series.rolling(window, min_periods=2).std(ddof=0).fillna(0).to_numpy()
        for origin_index in range(max_lag, len(frame) - max_horizon, origin_stride):
            origin = timestamps[origin_index]
            common: dict[str, Any] = {
                "station_id": station.station_id,
                "latitude": float(station.latitude),
                "longitude": float(station.longitude),
                "origin_timestamp": origin,
                **_time_features(origin, "origin"),
            }
            for variable_index, variable in enumerate(VARIABLES):
                for lag in LAG_STEPS:
                    common[f"{variable}_lag_{lag}"] = nasa[origin_index - lag, variable_index]
                for window in ROLLING_WINDOWS:
                    common[f"{variable}_mean_{window}"] = rolling[(variable_index, window, "mean")][origin_index]
                    common[f"{variable}_std_{window}"] = rolling[(variable_index, window, "std")][origin_index]
            for horizon_steps in HORIZONS:
                target_index = origin_index + horizon_steps
                target = timestamps[target_index]
                row = {
                    **common,
                    "target_timestamp": target,
                    "target_year": int(target.year),
                    "horizon_steps": float(horizon_steps),
                    "horizon_hours": float(horizon_steps * 3),
                    "horizon_bucket": horizon_bucket(horizon_steps),
                    **_time_features(target, "target"),
                }
                for variable_index, variable in enumerate(VARIABLES):
                    row[f"target_bmd_{variable}"] = bmd[target_index, variable_index]
                    row[f"target_nasa_{variable}"] = nasa[target_index, variable_index]
                rows.append(row)
        print(f"Prepared {station.station_id}: {len(rows):,} cumulative samples")
    data = pd.DataFrame(rows)
    return data.replace([np.inf, -np.inf], np.nan)


def fit_regressor(frame: pd.DataFrame, target: str) -> HistGradientBoostingRegressor:
    model = HistGradientBoostingRegressor(
        max_iter=140,
        max_leaf_nodes=31,
        learning_rate=0.07,
        l2_regularization=0.1,
        random_state=42,
    )
    valid = frame[target].notna()
    model.fit(frame.loc[valid, FEATURE_COLUMNS], frame.loc[valid, target])
    return model


def fit_rain(frame: pd.DataFrame) -> tuple[HistGradientBoostingClassifier, HistGradientBoostingRegressor]:
    target = frame["target_bmd_PRECTOTCORR"]
    valid = target.notna()
    classifier = HistGradientBoostingClassifier(
        max_iter=120,
        learning_rate=0.07,
        l2_regularization=0.1,
        random_state=42,
    )
    classifier.fit(frame.loc[valid, FEATURE_COLUMNS], (target.loc[valid] >= RAIN_THRESHOLD_MM).astype(int))
    positive = valid & (target >= RAIN_THRESHOLD_MM)
    regressor = HistGradientBoostingRegressor(
        max_iter=140,
        learning_rate=0.07,
        l2_regularization=0.1,
        random_state=42,
    )
    regressor.fit(frame.loc[positive, FEATURE_COLUMNS], np.log1p(target.loc[positive]))
    return classifier, regressor


def tune_rain_thresholds(model: Any, validation: pd.DataFrame) -> dict[str, float]:
    classifier, _ = model
    probability = classifier.predict_proba(validation[FEATURE_COLUMNS])[:, 1]
    observed = validation["target_bmd_PRECTOTCORR"].to_numpy(dtype=float)
    thresholds: dict[str, float] = {}
    for bucket in [label for _, _, label in HORIZON_BUCKETS]:
        selected = validation["horizon_bucket"].eq(bucket).to_numpy()
        wet = observed[selected] >= RAIN_THRESHOLD_MM
        bucket_probability = probability[selected]
        best_threshold = 0.5
        best_csi = -1.0
        for threshold in np.linspace(0.01, 0.50, 50):
            predicted_wet = bucket_probability >= threshold
            hits = int(np.sum(wet & predicted_wet))
            misses = int(np.sum(wet & ~predicted_wet))
            false_alarms = int(np.sum(~wet & predicted_wet))
            csi = hits / max(hits + misses + false_alarms, 1)
            if csi > best_csi:
                best_threshold = float(threshold)
                best_csi = csi
        thresholds[bucket] = best_threshold
    return thresholds


def predict_model(
    variable: str,
    model: Any,
    frame: pd.DataFrame,
    rain_thresholds: dict[str, float] | None = None,
) -> tuple[np.ndarray, np.ndarray | None]:
    if variable == "PRECTOTCORR":
        classifier, regressor = model
        probability = classifier.predict_proba(frame[FEATURE_COLUMNS])[:, 1]
        amount = np.maximum(0, np.expm1(regressor.predict(frame[FEATURE_COLUMNS])))
        if rain_thresholds:
            thresholds = frame["horizon_bucket"].map(rain_thresholds).fillna(0.5).to_numpy(dtype=float)
        else:
            thresholds = np.full(len(frame), 0.5, dtype=float)
        return np.where(probability >= thresholds, amount, 0.0), probability
    prediction = model.predict(frame[FEATURE_COLUMNS])
    if variable == "RH2M":
        prediction = np.clip(prediction, 0, 100)
    elif variable == "WS10M":
        prediction = np.maximum(0, prediction)
    return prediction, None


def strongest_baseline(variable: str, frame: pd.DataFrame, observed: np.ndarray) -> tuple[str, np.ndarray]:
    candidates = {
        "nasa_persistence": frame[f"{variable}_lag_0"].to_numpy(dtype=float),
        "nasa_daily_seasonal": frame[f"{variable}_lag_8"].to_numpy(dtype=float),
    }
    scores = {
        name: mean_squared_error(observed[np.isfinite(observed) & np.isfinite(values)], values[np.isfinite(observed) & np.isfinite(values)])
        for name, values in candidates.items()
    }
    name = min(scores, key=scores.get)
    return name, candidates[name]


def evaluate_split(
    split_name: str,
    variable: str,
    model: Any,
    frame: pd.DataFrame,
    rain_thresholds: dict[str, float] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    predicted, probability = predict_model(variable, model, frame, rain_thresholds)
    observed = frame[f"target_bmd_{variable}"].to_numpy(dtype=float)
    prediction_rows = frame[["station_id", "target_timestamp", "horizon_bucket", "target_season"]].copy()
    prediction_rows["variable"] = variable
    prediction_rows["split"] = split_name
    prediction_rows["observed"] = observed
    prediction_rows["predicted"] = predicted
    if probability is not None:
        prediction_rows["wet_probability"] = probability
    metrics: list[dict[str, Any]] = []
    for bucket in [label for _, _, label in HORIZON_BUCKETS]:
        selected = frame["horizon_bucket"].eq(bucket).to_numpy()
        bucket_observed = observed[selected]
        bucket_predicted = predicted[selected]
        baseline_name, baseline = strongest_baseline(variable, frame.loc[selected], bucket_observed)
        model_row = {
            "split": split_name,
            "variable": variable,
            "horizon_bucket": bucket,
            "candidate": "hist_gradient_direct",
            **metric_summary(bucket_observed, bucket_predicted),
        }
        baseline_row = {
            "split": split_name,
            "variable": variable,
            "horizon_bucket": bucket,
            "candidate": baseline_name,
            **metric_summary(bucket_observed, baseline),
        }
        if variable == "PRECTOTCORR":
            model_row.update(rain_metrics(bucket_observed, bucket_predicted, probability[selected] if probability is not None else None))
            baseline_row.update(rain_metrics(bucket_observed, baseline))
        metrics.extend((model_row, baseline_row))
    return pd.DataFrame(metrics), prediction_rows


def gate_horizons(metrics: pd.DataFrame) -> dict[str, dict[str, bool]]:
    enabled: dict[str, dict[str, bool]] = {variable: {} for variable in VARIABLES}
    for variable in VARIABLES:
        for _, _, bucket in HORIZON_BUCKETS:
            passes = True
            for split in ("validation_2023", "spatial_temporal_test_2024"):
                subset = metrics[
                    (metrics["variable"] == variable)
                    & (metrics["horizon_bucket"] == bucket)
                    & (metrics["split"] == split)
                ]
                model = subset[subset["candidate"] == "hist_gradient_direct"].iloc[0]
                baseline = subset[subset["candidate"] != "hist_gradient_direct"].iloc[0]
                improvement = 1 - float(model["rmse"]) / float(baseline["rmse"])
                bias_tolerance = max(BIAS_TOLERANCE_BY_VARIABLE[variable], abs(float(baseline["bias"])) * 0.1)
                passes &= improvement >= 0.05 and abs(float(model["bias"])) <= abs(float(baseline["bias"])) + bias_tolerance
                coverage = float(model.get("interval_coverage_90", math.nan))
                passes &= math.isfinite(coverage) and 0.75 <= coverage <= 0.99
                if variable == "PRECTOTCORR":
                    model_csi = float(model.get("csi", math.nan))
                    baseline_csi = float(baseline.get("csi", math.nan))
                    passes &= model_csi >= baseline_csi - 0.02
            enabled[variable][bucket] = bool(passes)
    return enabled


def residual_quantiles(predictions: pd.DataFrame) -> dict[str, dict[str, dict[str, float]]]:
    table: dict[str, dict[str, dict[str, float]]] = {}
    predictions = predictions.copy()
    predictions["residual"] = predictions["observed"] - predictions["predicted"]
    for variable in VARIABLES:
        variable_frame = predictions[predictions["variable"] == variable]
        entries: dict[str, dict[str, float]] = {}
        for bucket in [label for _, _, label in HORIZON_BUCKETS]:
            bucket_frame = variable_frame[variable_frame["horizon_bucket"] == bucket]
            for season in sorted(bucket_frame["target_season"].dropna().unique()):
                values = bucket_frame.loc[bucket_frame["target_season"] == season, "residual"].dropna()
                if len(values) >= 100:
                    entries[f"{bucket}|{int(season)}"] = {
                        "p05": float(values.quantile(0.05)),
                        "p50": float(values.quantile(0.50)),
                        "p95": float(values.quantile(0.95)),
                    }
            values = bucket_frame["residual"].dropna()
            entries[f"{bucket}|all"] = {
                "p05": float(values.quantile(0.05)),
                "p50": float(values.quantile(0.50)),
                "p95": float(values.quantile(0.95)),
            }
        values = variable_frame["residual"].dropna()
        entries["all|all"] = {
            "p05": float(values.quantile(0.05)),
            "p50": float(values.quantile(0.50)),
            "p95": float(values.quantile(0.95)),
        }
        safety_factor = INTERVAL_SAFETY_FACTORS.get(variable, 1.0)
        if safety_factor != 1.0:
            for interval in entries.values():
                median = interval["p50"]
                interval["p05"] = median + (interval["p05"] - median) * safety_factor
                interval["p95"] = median + (interval["p95"] - median) * safety_factor
        table[variable] = entries
    return table


def add_interval_metrics(
    metrics: pd.DataFrame,
    predictions: pd.DataFrame,
    quantiles: dict[str, dict[str, dict[str, float]]],
) -> pd.DataFrame:
    metrics = metrics.copy()
    metrics["interval_coverage_90"] = math.nan
    metrics["weighted_interval_score"] = math.nan
    alpha = 0.10
    for (split, variable, bucket), group in predictions.groupby(
        ["split", "variable", "horizon_bucket"], dropna=False
    ):
        observed = group["observed"].to_numpy(dtype=float)
        predicted = group["predicted"].to_numpy(dtype=float)
        lower = np.empty(len(group), dtype=float)
        median = np.empty(len(group), dtype=float)
        upper = np.empty(len(group), dtype=float)
        table = quantiles[variable]
        for index, season in enumerate(group["target_season"].to_numpy(dtype=int)):
            values = table.get(f"{bucket}|{season}") or table.get(f"{bucket}|all") or table["all|all"]
            lower[index] = predicted[index] + values["p05"]
            median[index] = predicted[index] + values["p50"]
            upper[index] = predicted[index] + values["p95"]
        if variable == "RH2M":
            lower, median, upper = (np.clip(array, 0, 100) for array in (lower, median, upper))
        elif variable in {"PRECTOTCORR", "WS10M"}:
            lower, median, upper = (np.maximum(0, array) for array in (lower, median, upper))
        valid = np.isfinite(observed) & np.isfinite(lower) & np.isfinite(median) & np.isfinite(upper)
        observed, lower, median, upper = (array[valid] for array in (observed, lower, median, upper))
        coverage = float(np.mean((observed >= lower) & (observed <= upper)))
        interval_score = (
            upper
            - lower
            + (2 / alpha) * (lower - observed) * (observed < lower)
            + (2 / alpha) * (observed - upper) * (observed > upper)
        )
        wis = float(np.mean((0.5 * np.abs(observed - median) + (alpha / 2) * interval_score) / 1.5))
        selected = (
            metrics["split"].eq(split)
            & metrics["variable"].eq(variable)
            & metrics["horizon_bucket"].eq(bucket)
            & metrics["candidate"].eq("hist_gradient_direct")
        )
        metrics.loc[selected, "interval_coverage_90"] = coverage
        metrics.loc[selected, "weighted_interval_score"] = wis
    return metrics


def write_report(
    path: Path,
    metrics: pd.DataFrame,
    enabled: dict[str, dict[str, bool]],
    elapsed: float,
    sota_benchmark: dict[str, Any] | None,
    chronos_accuracy: pd.DataFrame | None,
) -> None:
    chronos_section = "Chronos-2 was not benchmarked in this run."
    if sota_benchmark:
        chronos_section = (
            f"Chronos-2 CPU resource check: {sota_benchmark['predict_seconds']:.3f}s prediction, "
            f"{sota_benchmark['rss_mb']:.0f} MB RSS, gate passed={sota_benchmark['production_eligible']}."
        )
    if chronos_accuracy is not None and not chronos_accuracy.empty:
        selected = chronos_accuracy[
            chronos_accuracy["candidate"] == "chronos-2_plus_month_hour_bias"
        ]
        chronos_section += (
            " Its sampled 2024 unseen-station accuracy is recorded in "
            "`chronos2_accuracy_metrics.csv`. It remains supplemental because it has not "
            "completed the full 2023 model-selection protocol used by the packaged winner.\n\n"
            + selected[["variable", "horizon_bucket", "n", "bias", "mae", "rmse"]]
            .round(4)
            .to_markdown(index=False)
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# NASA/BMD Operational Forecast Validation\n\n"
        "Training data: scraped OGIMET BMD SYNOP station data paired with scraped NASA "
        "POWER station data. No Excel-derived BMD weather observations are used by this "
        "artifact.\n\n"
        "Leakage controls: 2021-2022 training, 2023 validation, 2024 final test on seven unseen stations.\n\n"
        f"Training runtime: {elapsed / 60:.1f} minutes.\n\n"
        "## Production quality gates\n\n"
        f"```json\n{json.dumps(enabled, indent=2)}\n```\n\n"
        "## Tournament results\n\n"
        f"{metrics.round(4).to_markdown(index=False)}\n\n"
        "## SOTA candidate registry\n\n"
        f"{chronos_section}\n\n"
        "TimeXer, iTransformer, and PatchTST are registered offline candidates. They must "
        "write metrics in this same schema and satisfy both the validation protocol and CPU "
        "serving gate before replacing the packaged winner.\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Train leakage-safe NASA-history to BMD operational forecasts.")
    parser.add_argument("--stations-json", type=Path, default=DEFAULT_STATIONS_JSON)
    parser.add_argument("--bmd-dir", type=Path, default=DEFAULT_BMD_DIR)
    parser.add_argument("--nasa-dir", type=Path, default=DEFAULT_NASA_DIR)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--table-dir", type=Path, default=DEFAULT_TABLE_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--origin-stride", type=int, default=8)
    parser.add_argument("--sota-benchmark", type=Path, default=DEFAULT_SOTA_BENCHMARK)
    parser.add_argument("--chronos-accuracy", type=Path, default=DEFAULT_CHRONOS_ACCURACY)
    args = parser.parse_args()

    started = time.perf_counter()
    stations = load_stations(args.stations_json)
    frames = load_station_timeseries(stations, args.bmd_dir, args.nasa_dir)
    data = build_dataset(stations, frames, args.origin_stride)
    train = data[(data["target_year"] <= 2022) & ~data["station_id"].isin(HOLDOUT_STATIONS)]
    validation = data[(data["target_year"] == 2023) & ~data["station_id"].isin(HOLDOUT_STATIONS)]
    test = data[(data["target_year"] == 2024) & data["station_id"].isin(HOLDOUT_STATIONS)]
    if train.empty or validation.empty or test.empty:
        raise RuntimeError("Temporal/spatial split produced an empty dataset.")

    selection_models: dict[str, Any] = {}
    nasa_models: dict[str, Any] = {}
    metrics_frames: list[pd.DataFrame] = []
    prediction_frames: list[pd.DataFrame] = []
    rain_probability_thresholds: dict[str, float] = {}
    for variable in VARIABLES:
        print(f"Fitting selection model for {variable}...")
        model = fit_rain(train) if variable == "PRECTOTCORR" else fit_regressor(train, f"target_bmd_{variable}")
        selection_models[variable] = model
        variable_rain_thresholds = None
        if variable == "PRECTOTCORR":
            rain_probability_thresholds = tune_rain_thresholds(model, validation)
            variable_rain_thresholds = rain_probability_thresholds
        for split_name, split_frame in (("validation_2023", validation), ("spatial_temporal_test_2024", test)):
            metrics, predictions = evaluate_split(
                split_name,
                variable,
                model,
                split_frame,
                variable_rain_thresholds,
            )
            metrics_frames.append(metrics)
            prediction_frames.append(predictions)

    predictions_all = pd.concat(prediction_frames, ignore_index=True)
    calibration_predictions = predictions_all[predictions_all["split"] == "validation_2023"]
    quantiles = residual_quantiles(calibration_predictions)
    metrics_all = add_interval_metrics(pd.concat(metrics_frames, ignore_index=True), predictions_all, quantiles)
    enabled = gate_horizons(metrics_all)

    print("Refitting production models on all paired data...")
    production_models: dict[str, Any] = {}
    for variable in VARIABLES:
        production_models[variable] = (
            fit_rain(data) if variable == "PRECTOTCORR" else fit_regressor(data, f"target_bmd_{variable}")
        )
        nasa_models[variable] = fit_regressor(data, f"target_nasa_{variable}")

    sota_benchmark = (
        json.loads(args.sota_benchmark.read_text(encoding="utf-8"))
        if args.sota_benchmark.exists()
        else None
    )
    chronos_accuracy = (
        pd.read_csv(args.chronos_accuracy)
        if args.chronos_accuracy.exists()
        else None
    )
    bundle = {
        "version": FORECAST_VERSION,
        "data_sources": {
            "bmd_observations": data_source_label(args.bmd_dir),
            "bmd_observations_kind": "scraped_ogimet_synop",
            "nasa_station_data": data_source_label(args.nasa_dir),
            "nasa_station_data_kind": "scraped_nasa_power",
            "excel_weather_observations_used": False,
        },
        "feature_columns": FEATURE_COLUMNS,
        "variables": VARIABLES,
        "max_forecast_hours": 96,
        "models": production_models,
        "nasa_models": nasa_models,
        "selected_models": {variable: "hist_gradient_direct" for variable in VARIABLES},
        "enabled_horizons": enabled,
        "rain_probability_thresholds": rain_probability_thresholds,
        "interval_safety_factors": INTERVAL_SAFETY_FACTORS,
        "residual_quantiles": quantiles,
        "holdout_stations": sorted(HOLDOUT_STATIONS),
        "tournament": {
            "evaluated": [
                "nasa_persistence",
                "nasa_daily_seasonal",
                "hist_gradient_direct",
                "chronos-2_supplemental",
            ],
            "resource_benchmark": sota_benchmark,
            "chronos_accuracy_rows": (
                json.loads(chronos_accuracy.to_json(orient="records"))
                if chronos_accuracy is not None
                else []
            ),
            "registered_offline": ["timexer", "itransformer", "patchtst"],
            "selection_rule": "best validated model subject to quality and CPU gates",
            "selected_reason": (
                "hist_gradient_direct completed the full 2023 selection and 2024 unseen-station "
                "test; Chronos-2 currently has only a supplemental sampled 2024 accuracy run"
            ),
        },
    }
    args.model_dir.mkdir(parents=True, exist_ok=True)
    args.table_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, args.model_dir / "model_bundle.joblib", compress=3)
    metadata = {key: value for key, value in bundle.items() if key not in {"models", "nasa_models", "residual_quantiles"}}
    (args.model_dir / "model_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    metrics_all.to_csv(args.table_dir / "tournament_metrics.csv", index=False)
    predictions_all.to_csv(args.table_dir / "holdout_predictions.csv", index=False)
    elapsed = time.perf_counter() - started
    write_report(args.report, metrics_all, enabled, elapsed, sota_benchmark, chronos_accuracy)
    print(f"Saved {args.model_dir / 'model_bundle.joblib'} in {elapsed / 60:.1f} minutes")


if __name__ == "__main__":
    main()
