from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import RidgeCV
from sklearn.metrics import accuracy_score, mean_absolute_error, mean_squared_error
from sklearn.model_selection import GroupKFold

from bias_correction_core import (
    DEFAULT_BMD_DIR,
    DEFAULT_MODEL_DIR,
    DEFAULT_NASA_DIR,
    DEFAULT_STATIONS_JSON,
    K_NEAREST,
    RAIN_THRESHOLD_MM,
    VARIABLES,
    build_feature_row,
    haversine_km,
    load_station_timeseries,
    load_stations,
    nearest_stations,
    season_code,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TABLE_DIR = PROJECT_ROOT / "outputs" / "tables" / "bias_correction"
DEFAULT_REPORT = PROJECT_ROOT / "outputs" / "reports" / "bias_correction_validation.md"
HOLDOUT_STATIONS = ["dhaka", "rangpur", "rajshahi", "sylhet", "khulna", "cox_s_bazar", "teknaf"]
DECAY_CANDIDATES_KM = [25.0, 50.0, 75.0, 100.0, 150.0, 200.0]
FEATURE_COLUMNS = [
    "nasa_value",
    "anchor_idw_bmd",
    "anchor_idw_nasa",
    "nasa_minus_anchor_idw_nasa",
    "latitude",
    "longitude",
    "month",
    "hour",
    "season",
    "sin_month",
    "cos_month",
    "sin_hour",
    "cos_hour",
    "idw_residual",
    "idw_corrected",
    "anchor1_bmd",
    "anchor1_nasa",
    "anchor1_residual",
    "anchor1_distance_km",
    "anchor2_bmd",
    "anchor2_nasa",
    "anchor2_residual",
    "anchor2_distance_km",
    "anchor3_bmd",
    "anchor3_nasa",
    "anchor3_residual",
    "anchor3_distance_km",
    "anchor4_bmd",
    "anchor4_nasa",
    "anchor4_residual",
    "anchor4_distance_km",
    "anchor5_bmd",
    "anchor5_nasa",
    "anchor5_residual",
    "anchor5_distance_km",
]
STACK_COLUMNS = [
    "nasa_value",
    "anchor_idw_bmd",
    "idw_corrected",
    "global_month_hour_bias",
    "month",
    "hour",
    "season",
    "nearest_distance_km",
]


def metric_summary(obs: pd.Series, pred: pd.Series) -> dict[str, float]:
    paired = pd.concat([obs, pred], axis=1).dropna()
    paired.columns = ["obs", "pred"]
    if paired.empty:
        return {
            "n": 0,
            "bias": math.nan,
            "mae": math.nan,
            "rmse": math.nan,
            "pearson_r": math.nan,
            "nse": math.nan,
        }
    diff = paired["pred"] - paired["obs"]
    obs_mean = paired["obs"].mean()
    den = float(((paired["obs"] - obs_mean) ** 2).sum())
    corr = (
        float(np.corrcoef(paired["obs"], paired["pred"])[0, 1])
        if len(paired) > 1 and paired["obs"].std(ddof=0) > 0 and paired["pred"].std(ddof=0) > 0
        else math.nan
    )
    return {
        "n": int(len(paired)),
        "bias": float(diff.mean()),
        "mae": float(mean_absolute_error(paired["obs"], paired["pred"])),
        "rmse": float(mean_squared_error(paired["obs"], paired["pred"]) ** 0.5),
        "pearson_r": corr,
        "nse": float(1 - (diff**2).sum() / den) if den else math.nan,
    }


def precipitation_event_metrics(obs: pd.Series, pred: pd.Series) -> dict[str, float]:
    paired = pd.concat([obs, pred], axis=1).dropna()
    paired.columns = ["obs", "pred"]
    if paired.empty:
        return {
            "wet_accuracy": math.nan,
            "pod": math.nan,
            "far": math.nan,
            "csi": math.nan,
            "frequency_bias": math.nan,
            "wet_amount_rmse": math.nan,
        }
    obs_wet = paired["obs"] >= RAIN_THRESHOLD_MM
    pred_wet = paired["pred"] >= RAIN_THRESHOLD_MM
    hits = int((obs_wet & pred_wet).sum())
    misses = int((obs_wet & ~pred_wet).sum())
    false_alarms = int((~obs_wet & pred_wet).sum())
    correct_negatives = int((~obs_wet & ~pred_wet).sum())
    wet_pairs = paired[obs_wet & pred_wet]
    return {
        "wet_accuracy": float((hits + correct_negatives) / len(paired)),
        "pod": hits / (hits + misses) if hits + misses else math.nan,
        "far": false_alarms / (hits + false_alarms) if hits + false_alarms else math.nan,
        "csi": hits / (hits + misses + false_alarms) if hits + misses + false_alarms else math.nan,
        "frequency_bias": (hits + false_alarms) / (hits + misses) if hits + misses else math.nan,
        "wet_amount_rmse": float(mean_squared_error(wet_pairs["obs"], wet_pairs["pred"]) ** 0.5)
        if not wet_pairs.empty
        else math.nan,
    }


def audit_nasa_precip(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for station_id, df in frames.items():
        rain = df["PRECTOTCORR_nasa"].dropna()
        rows.append(
            {
                "station_id": station_id,
                "n": len(rain),
                "mean": rain.mean(),
                "p95": rain.quantile(0.95),
                "p99": rain.quantile(0.99),
                "p999": rain.quantile(0.999),
                "max": rain.max(),
                "values_gt_250mm_obs_hour": int((rain > 250).sum()),
            }
        )
    return pd.DataFrame(rows)


def build_variable_dataset(
    variable: str,
    *,
    stations: list[Any],
    frames: dict[str, pd.DataFrame],
    decay_km: float,
) -> pd.DataFrame:
    station_by_id = {station.station_id: station for station in stations}
    rows: list[pd.DataFrame] = []
    key_columns = ["YEAR", "MO", "DY", "HR", "timestamp"]

    for target in stations:
        target_frame = frames[target.station_id][key_columns + [f"{variable}_bmd", f"{variable}_nasa"]].copy()
        target_frame = target_frame.rename(
            columns={f"{variable}_bmd": "target_bmd", f"{variable}_nasa": "nasa_value"}
        )
        target_frame["target_station_id"] = target.station_id
        target_frame["latitude"] = target.latitude
        target_frame["longitude"] = target.longitude
        target_frame["month"] = target_frame["MO"].astype(float)
        target_frame["hour"] = target_frame["HR"].astype(float)
        target_frame["season"] = target_frame["MO"].map(lambda month: float(season_code(int(month))))
        target_frame["sin_month"] = np.sin(2 * np.pi * target_frame["MO"] / 12)
        target_frame["cos_month"] = np.cos(2 * np.pi * target_frame["MO"] / 12)
        target_frame["sin_hour"] = np.sin(2 * np.pi * target_frame["HR"] / 24)
        target_frame["cos_hour"] = np.cos(2 * np.pi * target_frame["HR"] / 24)

        anchors = nearest_stations(
            target.latitude,
            target.longitude,
            stations,
            exclude_station_id=target.station_id,
            k=K_NEAREST,
        )
        for index, (anchor, distance) in enumerate(anchors, start=1):
            anchor_frame = frames[anchor.station_id][
                key_columns + [f"{variable}_bmd", f"{variable}_nasa"]
            ].copy()
            anchor_frame = anchor_frame.rename(
                columns={
                    f"{variable}_bmd": f"anchor{index}_bmd",
                    f"{variable}_nasa": f"anchor{index}_nasa",
                }
            )
            target_frame = target_frame.merge(anchor_frame, on=key_columns, how="left")
            target_frame[f"anchor{index}_distance_km"] = distance
            target_frame[f"anchor{index}_residual"] = (
                target_frame[f"anchor{index}_bmd"] - target_frame[f"anchor{index}_nasa"]
            )
        for index in range(len(anchors) + 1, K_NEAREST + 1):
            target_frame[f"anchor{index}_bmd"] = np.nan
            target_frame[f"anchor{index}_nasa"] = np.nan
            target_frame[f"anchor{index}_distance_km"] = np.nan
            target_frame[f"anchor{index}_residual"] = np.nan

        residual_values = []
        weight_values = []
        for index in range(1, K_NEAREST + 1):
            residual_values.append(target_frame[f"anchor{index}_residual"].to_numpy(dtype=float))
            distances = target_frame[f"anchor{index}_distance_km"].to_numpy(dtype=float)
            weight_values.append(np.exp(-np.maximum(distances, 0.01) / decay_km) / np.maximum(distances, 1.0))
        residual_matrix = np.vstack(residual_values).T
        weight_matrix = np.vstack(weight_values).T
        valid = np.isfinite(residual_matrix)
        weighted_sum = np.nansum(np.where(valid, residual_matrix * weight_matrix, 0.0), axis=1)
        weight_sum = np.nansum(np.where(valid, weight_matrix, 0.0), axis=1)
        target_frame["idw_residual"] = np.divide(
            weighted_sum,
            weight_sum,
            out=np.zeros_like(weighted_sum),
            where=weight_sum != 0,
        )
        bmd_matrix = np.vstack(
            [target_frame[f"anchor{index}_bmd"].to_numpy(dtype=float) for index in range(1, K_NEAREST + 1)]
        ).T
        nasa_matrix = np.vstack(
            [target_frame[f"anchor{index}_nasa"].to_numpy(dtype=float) for index in range(1, K_NEAREST + 1)]
        ).T
        bmd_valid = np.isfinite(bmd_matrix)
        nasa_valid = np.isfinite(nasa_matrix)
        target_frame["anchor_idw_bmd"] = np.divide(
            np.nansum(np.where(bmd_valid, bmd_matrix * weight_matrix, 0.0), axis=1),
            np.nansum(np.where(bmd_valid, weight_matrix, 0.0), axis=1),
            out=np.full(len(target_frame), np.nan),
            where=np.nansum(np.where(bmd_valid, weight_matrix, 0.0), axis=1) != 0,
        )
        target_frame["anchor_idw_nasa"] = np.divide(
            np.nansum(np.where(nasa_valid, nasa_matrix * weight_matrix, 0.0), axis=1),
            np.nansum(np.where(nasa_valid, weight_matrix, 0.0), axis=1),
            out=np.full(len(target_frame), np.nan),
            where=np.nansum(np.where(nasa_valid, weight_matrix, 0.0), axis=1) != 0,
        )
        target_frame["nasa_minus_anchor_idw_nasa"] = target_frame["nasa_value"] - target_frame["anchor_idw_nasa"]
        target_frame["idw_corrected"] = target_frame["nasa_value"] + target_frame["idw_residual"]
        target_frame["nearest_station_id"] = anchors[0][0].station_id
        target_frame["nearest_station_name"] = station_by_id[anchors[0][0].station_id].station_name
        target_frame["nearest_distance_km"] = anchors[0][1]
        rows.append(target_frame)

    data = pd.concat(rows, ignore_index=True)
    data = data.dropna(subset=["target_bmd", "nasa_value"])
    return data


def global_bias_predict(train: pd.DataFrame, test: pd.DataFrame) -> pd.Series:
    grouped = train.assign(residual=train["target_bmd"] - train["nasa_value"]).groupby(["MO", "HR"])["residual"].mean()
    fallback = float((train["target_bmd"] - train["nasa_value"]).mean())
    offsets = [
        grouped.get((int(row.MO), int(row.HR)), fallback)
        for row in test[["MO", "HR"]].itertuples(index=False)
    ]
    return test["nasa_value"].reset_index(drop=True) + pd.Series(offsets)


def global_bias_artifact(train: pd.DataFrame) -> dict[str, Any]:
    table = (
        train.assign(residual=train["target_bmd"] - train["nasa_value"])
        .groupby(["MO", "HR"])["residual"]
        .mean()
        .reset_index()
    )
    return {
        "offsets": {
            f"{int(row.MO)}-{int(row.HR)}": float(row.residual)
            for row in table.itertuples(index=False)
        },
        "fallback": float((train["target_bmd"] - train["nasa_value"]).mean()),
    }


def train_regressor(train: pd.DataFrame) -> HistGradientBoostingRegressor:
    model = HistGradientBoostingRegressor(
        max_iter=120,
        learning_rate=0.08,
        l2_regularization=0.05,
        random_state=42,
    )
    model.fit(train[FEATURE_COLUMNS], train["target_bmd"])
    return model


def stack_frame(data: pd.DataFrame, global_prediction: np.ndarray | pd.Series) -> pd.DataFrame:
    frame = data[
        [
            "nasa_value",
            "anchor_idw_bmd",
            "idw_corrected",
            "month",
            "hour",
            "season",
            "nearest_distance_km",
        ]
    ].copy()
    frame["global_month_hour_bias"] = np.asarray(global_prediction)
    frame = frame[STACK_COLUMNS]
    return frame.fillna(frame.median(numeric_only=True))


def train_linear_stack(train: pd.DataFrame) -> dict[str, Any]:
    global_prediction = global_bias_predict(train, train)
    x_train = stack_frame(train, global_prediction)
    model = RidgeCV(alphas=[0.01, 0.1, 1.0, 10.0, 100.0])
    model.fit(x_train, train["target_bmd"])
    return {
        "model": model,
        "columns": STACK_COLUMNS,
        "medians": {column: float(value) for column, value in x_train.median(numeric_only=True).items()},
        "global_bias": global_bias_artifact(train),
    }


def predict_linear_stack(artifact: dict[str, Any], data: pd.DataFrame, global_prediction: np.ndarray | pd.Series) -> np.ndarray:
    x_data = stack_frame(data, global_prediction)
    for column, value in artifact["medians"].items():
        x_data[column] = x_data[column].fillna(value)
    return artifact["model"].predict(x_data[artifact["columns"]])


def train_rain_models(train: pd.DataFrame) -> tuple[HistGradientBoostingClassifier, HistGradientBoostingRegressor]:
    classifier = HistGradientBoostingClassifier(
        max_iter=100,
        learning_rate=0.08,
        l2_regularization=0.05,
        random_state=42,
    )
    wet = (train["target_bmd"] >= RAIN_THRESHOLD_MM).astype(int)
    classifier.fit(train[FEATURE_COLUMNS], wet)

    positive = train[train["target_bmd"] >= RAIN_THRESHOLD_MM].copy()
    regressor = HistGradientBoostingRegressor(
        max_iter=120,
        learning_rate=0.08,
        l2_regularization=0.05,
        random_state=42,
    )
    if positive.empty:
        positive = train.copy()
    regressor.fit(positive[FEATURE_COLUMNS], np.log1p(positive["target_bmd"]))
    return classifier, regressor


def predict_rain(
    classifier: HistGradientBoostingClassifier,
    regressor: HistGradientBoostingRegressor,
    frame: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray]:
    wet_prob = classifier.predict_proba(frame[FEATURE_COLUMNS])[:, 1]
    amount = np.expm1(regressor.predict(frame[FEATURE_COLUMNS]))
    return wet_prob, np.where(wet_prob >= 0.5, amount, 0.0)


def grouped_cv_scores(data: pd.DataFrame, variable: str) -> pd.DataFrame:
    groups = data["target_station_id"]
    splits = GroupKFold(n_splits=min(5, groups.nunique()))
    rows = []
    for fold, (train_idx, test_idx) in enumerate(splits.split(data, groups=groups), start=1):
        train = data.iloc[train_idx]
        test = data.iloc[test_idx]
        predictions: dict[str, pd.Series | np.ndarray] = {
            "raw_nasa": test["nasa_value"].to_numpy(),
            "anchor_idw_bmd": test["anchor_idw_bmd"].to_numpy(),
            "global_month_hour_bias": global_bias_predict(train, test).to_numpy(),
            "idw_residual": test["idw_corrected"].to_numpy(),
        }
        stack_artifact = train_linear_stack(train)
        stack_pred = predict_linear_stack(stack_artifact, test, predictions["global_month_hour_bias"])
        if variable == "PRECTOTCORR":
            stack_pred = np.clip(stack_pred, 0.0, None)
        predictions["linear_stack"] = stack_pred
        if variable == "PRECTOTCORR":
            clf, reg = train_rain_models(train)
            wet_prob, pred = predict_rain(clf, reg, test)
            predictions["ml_two_stage"] = pred
        else:
            model = train_regressor(train)
            predictions["ml_regressor"] = model.predict(test[FEATURE_COLUMNS])
        for model_name, pred in predictions.items():
            row = {
                "fold": fold,
                "variable": variable,
                "model": model_name,
                **metric_summary(test["target_bmd"], pd.Series(pred, index=test.index)),
            }
            if variable == "PRECTOTCORR":
                row.update(precipitation_event_metrics(test["target_bmd"], pd.Series(pred, index=test.index)))
            rows.append(row)
    return pd.DataFrame(rows)


def choose_decay(variable: str, stations: list[Any], frames: dict[str, pd.DataFrame]) -> tuple[float, pd.DataFrame]:
    rows = []
    for decay in DECAY_CANDIDATES_KM:
        data = build_variable_dataset(variable, stations=stations, frames=frames, decay_km=decay)
        groups = data["target_station_id"]
        splits = GroupKFold(n_splits=min(5, groups.nunique()))
        for fold, (train_idx, test_idx) in enumerate(splits.split(data, groups=groups), start=1):
            test = data.iloc[test_idx]
            row = {
                "fold": fold,
                "variable": variable,
                "model": "idw_residual",
                **metric_summary(test["target_bmd"], test["idw_corrected"]),
            }
            if variable == "PRECTOTCORR":
                row.update(precipitation_event_metrics(test["target_bmd"], test["idw_corrected"]))
            row["decay_km"] = decay
            rows.append(row)
    scores = pd.DataFrame(rows)
    mean_scores = scores.groupby("decay_km", as_index=False)["rmse"].mean()
    best = float(mean_scores.sort_values("rmse").iloc[0]["decay_km"])
    return best, scores


def final_holdout_evaluation(
    data: pd.DataFrame,
    variable: str,
    selected_model_name: str,
) -> tuple[pd.DataFrame, pd.DataFrame, Any]:
    train = data[~data["target_station_id"].isin(HOLDOUT_STATIONS)].copy()
    holdout = data[data["target_station_id"].isin(HOLDOUT_STATIONS)].copy()
    predictions: dict[str, np.ndarray] = {
        "raw_nasa": holdout["nasa_value"].to_numpy(),
        "anchor_idw_bmd": holdout["anchor_idw_bmd"].to_numpy(),
        "global_month_hour_bias": global_bias_predict(train, holdout).to_numpy(),
        "idw_residual": holdout["idw_corrected"].to_numpy(),
    }
    stack_artifact = train_linear_stack(train)
    stack_pred = predict_linear_stack(stack_artifact, holdout, predictions["global_month_hour_bias"])
    if variable == "PRECTOTCORR":
        stack_pred = np.clip(stack_pred, 0.0, None)
    predictions["linear_stack"] = stack_pred
    model_artifact: Any
    if variable == "PRECTOTCORR":
        clf, reg = train_rain_models(train)
        wet_prob, ml_pred = predict_rain(clf, reg, holdout)
        predictions["ml_two_stage"] = ml_pred
        model_artifact = {"classifier": clf, "regressor": reg}
        holdout["wet_probability"] = wet_prob
    else:
        model = train_regressor(train)
        predictions["ml_regressor"] = model.predict(holdout[FEATURE_COLUMNS])
        model_artifact = model

    rows = []
    prediction_rows = holdout[
        [
            "target_station_id",
            "timestamp",
            "MO",
            "HR",
            "season",
            "nearest_station_id",
            "nearest_distance_km",
            "target_bmd",
            "nasa_value",
        ]
    ].copy()
    for name, pred in predictions.items():
        row = {"variable": variable, "model": name, **metric_summary(holdout["target_bmd"], pd.Series(pred, index=holdout.index))}
        if variable == "PRECTOTCORR":
            row.update(precipitation_event_metrics(holdout["target_bmd"], pd.Series(pred, index=holdout.index)))
        rows.append(row)
        prediction_rows[f"prediction_{name}"] = pred
    prediction_rows["prediction_selected"] = predictions[selected_model_name]
    prediction_rows["residual_selected"] = prediction_rows["prediction_selected"] - prediction_rows["target_bmd"]
    return pd.DataFrame(rows), prediction_rows, model_artifact


def distance_bucket(distance_km: float) -> str:
    if distance_km < 25:
        return "0-25"
    if distance_km < 50:
        return "25-50"
    if distance_km < 100:
        return "50-100"
    if distance_km < 150:
        return "100-150"
    if distance_km < 250:
        return "150-250"
    return "250+"


def select_model_from_cv(variable: str, cv_scores: pd.DataFrame) -> str:
    means = cv_scores.groupby("model", as_index=False).mean(numeric_only=True)
    if variable == "PRECTOTCORR":
        eligible = means[
            (means["wet_accuracy"] >= 0.85)
            & (means["frequency_bias"] >= 0.4)
            & (means["frequency_bias"] <= 2.0)
        ]
        if not eligible.empty:
            return str(eligible.sort_values("rmse").iloc[0]["model"])
    return str(means.sort_values("rmse").iloc[0]["model"])


def write_report(path: Path, holdout_metrics: pd.DataFrame, selected: dict[str, str], decays: dict[str, float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = holdout_metrics.round(4).to_markdown(index=False)
    text = f"""# Bias-Correction Validation

Training data: official BMD/NASA paired station data, 2021-2024, 3-hour UTC steps.

Final isolated holdout stations: {", ".join(HOLDOUT_STATIONS)}

Selected models:

{json.dumps(selected, indent=2)}

Selected distance decay lengths in km:

{json.dumps(decays, indent=2)}

## Holdout Metrics

{table}
"""
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and validate NASA-BMD bias-correction models.")
    parser.add_argument("--stations-json", type=Path, default=DEFAULT_STATIONS_JSON)
    parser.add_argument("--bmd-dir", type=Path, default=DEFAULT_BMD_DIR)
    parser.add_argument("--nasa-dir", type=Path, default=DEFAULT_NASA_DIR)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--table-dir", type=Path, default=DEFAULT_TABLE_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    stations = load_stations(args.stations_json)
    frames = load_station_timeseries(stations, args.bmd_dir, args.nasa_dir)
    args.model_dir.mkdir(parents=True, exist_ok=True)
    args.table_dir.mkdir(parents=True, exist_ok=True)

    audit = audit_nasa_precip(frames)
    audit.to_csv(args.table_dir / "nasa_precip_outlier_audit.csv", index=False)

    selected_models: dict[str, str] = {}
    selected_decays: dict[str, float] = {}
    cv_frames = []
    holdout_frames = []
    holdout_predictions = []
    model_artifacts: dict[str, Any] = {}

    for variable in VARIABLES:
        print(f"Selecting distance decay for {variable}...")
        decay, decay_scores = choose_decay(variable, stations, frames)
        selected_decays[variable] = decay
        decay_scores.to_csv(args.table_dir / f"{variable}_decay_cv_scores.csv", index=False)

        print(f"Training and cross-validating {variable} with decay={decay} km...")
        data = build_variable_dataset(variable, stations=stations, frames=frames, decay_km=decay)
        cv_scores = grouped_cv_scores(data[~data["target_station_id"].isin(HOLDOUT_STATIONS)].copy(), variable)
        cv_frames.append(cv_scores)
        selected_model = select_model_from_cv(variable, cv_scores)
        selected_models[variable] = selected_model

        holdout_metrics, predictions, artifact = final_holdout_evaluation(data, variable, selected_model)
        holdout_frames.append(holdout_metrics)
        holdout_predictions.append(predictions.assign(variable=variable))
        model_artifacts[variable] = artifact

        print(f"{variable}: selected={selected_model}, holdout rows={len(predictions)}")

    cv_all = pd.concat(cv_frames, ignore_index=True)
    holdout_all = pd.concat(holdout_frames, ignore_index=True)
    predictions_all = pd.concat(holdout_predictions, ignore_index=True)
    residuals = predictions_all[
        ["variable", "season", "nearest_distance_km", "residual_selected"]
    ].rename(columns={"residual_selected": "residual"})
    residuals["distance_bucket"] = residuals["nearest_distance_km"].map(distance_bucket)

    cv_all.to_csv(args.table_dir / "model_cv_metrics.csv", index=False)
    holdout_all.to_csv(args.table_dir / "holdout_metrics.csv", index=False)
    predictions_all.to_csv(args.table_dir / "holdout_predictions.csv", index=False)
    residuals.to_csv(args.table_dir / "validation_residuals.csv", index=False)

    full_model_artifacts: dict[str, Any] = {}
    for variable in VARIABLES:
        data = build_variable_dataset(variable, stations=stations, frames=frames, decay_km=selected_decays[variable])
        if selected_models[variable] == "ml_two_stage":
            full_model_artifacts[variable] = train_rain_models(data)
        elif selected_models[variable] == "ml_regressor":
            full_model_artifacts[variable] = train_regressor(data)
        elif selected_models[variable] == "global_month_hour_bias":
            full_model_artifacts[variable] = global_bias_artifact(data)
        elif selected_models[variable] == "linear_stack":
            full_model_artifacts[variable] = train_linear_stack(data)
        else:
            full_model_artifacts[variable] = None

    bundle = {
        "version": "bias-correction-v1",
        "feature_columns": FEATURE_COLUMNS,
        "variables": VARIABLES,
        "holdout_stations": HOLDOUT_STATIONS,
        "selected_models": selected_models,
        "selected_decays_km": selected_decays,
        "models": full_model_artifacts,
        "stations": [station.__dict__ for station in stations],
        "validation_residuals": residuals,
        "rain_threshold_mm": RAIN_THRESHOLD_MM,
    }
    joblib.dump(bundle, args.model_dir / "model_bundle.joblib")
    (args.model_dir / "model_metadata.json").write_text(
        json.dumps(
            {
                "version": bundle["version"],
                "feature_columns": FEATURE_COLUMNS,
                "variables": VARIABLES,
                "holdout_stations": HOLDOUT_STATIONS,
                "selected_models": selected_models,
                "selected_decays_km": selected_decays,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    write_report(args.report, holdout_all, selected_models, selected_decays)
    print(f"Saved model bundle: {args.model_dir / 'model_bundle.joblib'}")
    print(f"Saved validation report: {args.report}")


if __name__ == "__main__":
    main()
