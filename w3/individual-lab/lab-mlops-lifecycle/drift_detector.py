"""Detect data drift and labeled performance degradation for the lifecycle lab."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import mlflow
import mlflow.pyfunc
import pandas as pd
from evidently.metric_preset import DataDriftPreset
from evidently.report import Report

from metrics_util import push_drift_score, push_model_eval
from pipeline import FEATURES, MODEL_NAME

DEFAULT_THRESHOLD = 0.15
DEFAULT_PERF_THRESHOLD = 0.70
REPORT_DIR = Path("outputs/drift_reports")


@dataclass
class DriftResult:
    score: float
    is_drift: bool
    threshold: float
    drifted_features: list[str]
    report_path: Path | None
    timestamp: str
    perf_precision: float | None = None
    perf_recall: float | None = None
    perf_is_degraded: bool = False
    perf_threshold: float = DEFAULT_PERF_THRESHOLD


def _feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in FEATURES if column not in df.columns]
    if missing:
        raise ValueError(f"Missing feature columns: {missing}")
    return df[FEATURES].dropna()


def detect_drift(
    reference_df: pd.DataFrame,
    current_df: pd.DataFrame,
    threshold: float = DEFAULT_THRESHOLD,
    report_label: str = "",
) -> DriftResult:
    report = Report(metrics=[DataDriftPreset()])
    report.run(reference_data=_feature_frame(reference_df), current_data=_feature_frame(current_df))
    result = report.as_dict()["metrics"][0]["result"]

    score = float(result.get("share_of_drifted_columns", 0.0))
    drift_by_columns = result.get("drift_by_columns", {})
    drifted_features = [
        feature for feature, info in drift_by_columns.items() if info.get("drift_detected", False)
    ]

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    label = f"-{report_label}" if report_label else ""
    report_path = REPORT_DIR / f"drift-report{label}-{timestamp}.html"
    report.save_html(str(report_path))

    return DriftResult(
        score=score,
        is_drift=score > threshold,
        threshold=threshold,
        drifted_features=drifted_features,
        report_path=report_path,
        timestamp=timestamp,
    )


def precision_recall(y_true, y_pred) -> tuple[float, float]:
    tp = int(((y_pred == 1) & (y_true == 1)).sum())
    fp = int(((y_pred == 1) & (y_true == 0)).sum())
    fn = int(((y_pred == 0) & (y_true == 1)).sum())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return precision, recall


def normalize_predictions(raw_predictions) -> pd.Series:
    values = pd.Series(raw_predictions)
    if set(values.unique()).issubset({-1, 1}):
        return (values == -1).astype(int)
    return values.astype(int)


def check_performance_drift(
    labeled_df: pd.DataFrame,
    model_uri: str = f"models:/{MODEL_NAME}@production",
    perf_threshold: float = DEFAULT_PERF_THRESHOLD,
) -> tuple[float, float, bool]:
    if "anomaly_label" not in labeled_df.columns:
        raise ValueError("labeled data must contain anomaly_label")
    model = mlflow.pyfunc.load_model(model_uri)
    features = _feature_frame(labeled_df)
    y_true = labeled_df.loc[features.index, "anomaly_label"].astype(int)
    raw_predictions = model.predict(features)
    y_pred = normalize_predictions(raw_predictions)
    precision, recall = precision_recall(y_true.reset_index(drop=True), y_pred.reset_index(drop=True))
    return precision, recall, precision < perf_threshold


def log_to_mlflow(result: DriftResult, experiment_name: str = "anomaly-detection-drift") -> None:
    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000"))
    mlflow.set_experiment(experiment_name)
    with mlflow.start_run(run_name=f"drift-check-{result.timestamp}"):
        mlflow.log_metric("drift_score", result.score)
        mlflow.log_metric("is_drift", float(result.is_drift))
        mlflow.log_param("threshold", result.threshold)
        mlflow.log_param("drifted_features", ",".join(result.drifted_features) or "none")
        if result.report_path:
            mlflow.log_artifact(str(result.report_path), artifact_path="drift_reports")
        if result.perf_precision is not None and result.perf_recall is not None:
            mlflow.log_metric("perf_precision", result.perf_precision)
            mlflow.log_metric("perf_recall", result.perf_recall)
            mlflow.log_metric("perf_is_degraded", float(result.perf_is_degraded))


def run_check(args: argparse.Namespace) -> DriftResult:
    reference_df = pd.read_csv(args.reference)
    current_df = pd.read_csv(args.current)

    if args.check_mode in {"data", "combined"}:
        result = detect_drift(reference_df, current_df, args.threshold)
        print(f"Drift score: {result.score:.4f}")
        print(f"Drift threshold: {result.threshold:.4f}")
        print(f"Drift detected: {result.is_drift}")
        print(f"Drifted features: {result.drifted_features}")
        print(f"Report saved: {result.report_path}")
    else:
        result = DriftResult(
            score=0.0,
            is_drift=False,
            threshold=args.threshold,
            drifted_features=[],
            report_path=None,
            timestamp=datetime.utcnow().strftime("%Y%m%d-%H%M%S"),
        )

    if args.check_mode in {"performance", "combined"}:
        if not args.labeled_current:
            raise ValueError("--labeled-current is required for performance or combined mode")
        labeled_df = pd.read_csv(args.labeled_current)
        precision, recall, degraded = check_performance_drift(
            labeled_df=labeled_df,
            model_uri=args.model_uri,
            perf_threshold=args.perf_threshold,
        )
        result.perf_precision = precision
        result.perf_recall = recall
        result.perf_is_degraded = degraded
        result.perf_threshold = args.perf_threshold
        print(f"Perf precision: {precision:.4f}")
        print(f"Perf recall: {recall:.4f}")
        print(f"Perf degraded: {degraded}")

    if args.log_mlflow:
        log_to_mlflow(result)

    try:
        push_drift_score(result.score, result.threshold)
        if result.perf_precision is not None and result.perf_recall is not None:
            f1 = (
                2 * result.perf_precision * result.perf_recall / (result.perf_precision + result.perf_recall)
                if (result.perf_precision + result.perf_recall)
                else 0.0
            )
            push_model_eval("current", result.perf_precision, result.perf_recall, f1)
    except Exception as exc:
        print(f"[drift_detector] WARNING: metric push skipped: {exc}")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect drift between reference and current data")
    parser.add_argument("--reference", default="data-pack/data/baseline.csv")
    parser.add_argument("--current", default="data-pack/data/drifted.csv")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--check-mode", choices=["data", "performance", "combined"], default="data")
    parser.add_argument("--labeled-current")
    parser.add_argument("--model-uri", default=f"models:/{MODEL_NAME}@production")
    parser.add_argument("--perf-threshold", type=float, default=DEFAULT_PERF_THRESHOLD)
    parser.add_argument("--log-mlflow", action="store_true")
    args = parser.parse_args()

    result = run_check(args)
    any_drift = result.is_drift or result.perf_is_degraded
    raise SystemExit(1 if any_drift else 0)


if __name__ == "__main__":
    main()
