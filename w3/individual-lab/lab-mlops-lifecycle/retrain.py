"""Drift-triggered retraining, approval, promotion, and rollback orchestrator."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import mlflow
import mlflow.sklearn
import pandas as pd
import requests
from mlflow import MlflowClient
from sklearn.ensemble import IsolationForest

from drift_detector import detect_drift, log_to_mlflow, normalize_predictions, precision_recall
from metrics_util import push_active_version, push_event, push_model_eval
from pipeline import EXPERIMENT_NAME, FEATURES, MODEL_NAME

AUDIT_LOG_PATH = Path("outputs/audit_log.jsonl")
POST_DEPLOY_CYCLES = 24
POST_DEPLOY_PRECISION_THRESHOLD = 0.65


def tracking_uri() -> str:
    return os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")


def append_audit(event: str, **fields) -> None:
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "event": event,
        **fields,
    }
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    return df[FEATURES].dropna()


def train_model(df: pd.DataFrame, contamination: float, n_estimators: int) -> tuple[IsolationForest, float, int]:
    features = feature_frame(df)
    model = IsolationForest(
        contamination=contamination,
        n_estimators=n_estimators,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(features)
    anomaly_rate = float((model.predict(features) == -1).mean())
    return model, anomaly_rate, len(features)


def evaluate_model(model, labeled_df: pd.DataFrame) -> tuple[float, float]:
    if "anomaly_label" not in labeled_df.columns:
        raise ValueError("evaluation data must contain anomaly_label")
    features = feature_frame(labeled_df)
    y_true = labeled_df.loc[features.index, "anomaly_label"].astype(int).reset_index(drop=True)
    raw_predictions = model.predict(features)
    y_pred = normalize_predictions(raw_predictions).reset_index(drop=True)
    return precision_recall(y_true, y_pred)


def load_mlflow_model(version_or_alias: str):
    return mlflow.sklearn.load_model(f"models:/{MODEL_NAME}@{version_or_alias}")


def f1_score(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def register_staging_model(
    model,
    training_rows: int,
    anomaly_rate: float,
    drift_score: float,
    input_example: pd.DataFrame,
) -> str:
    mlflow.set_tracking_uri(tracking_uri())
    mlflow.set_experiment(EXPERIMENT_NAME)
    with mlflow.start_run(run_name="retrain-triggered"):
        mlflow.log_param("trigger", "drift_detected")
        mlflow.log_param("training_rows", training_rows)
        mlflow.log_param("features", ",".join(FEATURES))
        mlflow.log_metric("drift_score", drift_score)
        mlflow.log_metric("train_anomaly_rate", anomaly_rate)
        mlflow.sklearn.log_model(
            sk_model=model,
            artifact_path="model",
            registered_model_name=MODEL_NAME,
            input_example=input_example.head(3),
        )

    client = MlflowClient(tracking_uri=tracking_uri())
    latest = max(client.search_model_versions(f"name='{MODEL_NAME}'"), key=lambda item: int(item.version))
    client.set_registered_model_alias(MODEL_NAME, "staging", latest.version)
    append_audit("model_registered_staging", staging_version=latest.version)
    print(f"[retrain] Registered {MODEL_NAME} v{latest.version} -> @staging")
    return str(latest.version)


def reload_serve(serve_url: str) -> bool:
    try:
        response = requests.post(f"{serve_url}/reload", timeout=10)
        response.raise_for_status()
        print(f"[retrain] serve.py reloaded: {response.json()}")
        append_audit("production_reloaded", serve_url=serve_url, response=response.json())
        return True
    except requests.RequestException as exc:
        print(f"[retrain] WARNING: serve reload failed: {exc}")
        append_audit("production_reload_failed", serve_url=serve_url, error=str(exc))
        return False


def promote(staging_version: str, previous_production_version: str, serve_url: str) -> None:
    client = MlflowClient(tracking_uri=tracking_uri())
    client.set_registered_model_alias(MODEL_NAME, "production", staging_version)
    append_audit(
        "promotion_approved",
        promoted_version=staging_version,
        previous_production_version=previous_production_version,
    )
    print(f"[retrain] Promoted v{staging_version} -> @production")
    reload_serve(serve_url)
    try:
        push_event("retrain_triggered", staging_version)
        push_active_version(staging_version, "production")
    except Exception as exc:
        print(f"[retrain] WARNING: metric push skipped: {exc}")


def post_deploy_monitor(
    v2_version: str,
    v1_version: str,
    eval_path: str,
    serve_url: str,
    cycles: int = POST_DEPLOY_CYCLES,
    precision_threshold: float = POST_DEPLOY_PRECISION_THRESHOLD,
) -> None:
    eval_df = pd.read_csv(eval_path)
    client = MlflowClient(tracking_uri=tracking_uri())

    for cycle in range(1, cycles + 1):
        model = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}@production")
        precision, recall = evaluate_model(model, eval_df)
        print(f"post_deploy_monitor Cycle {cycle:02d}/{cycles} — precision: {precision:.4f}  recall: {recall:.4f}")
        append_audit(
            "post_deploy_monitor_cycle",
            cycle=cycle,
            version=v2_version,
            precision=precision,
            recall=recall,
        )
        try:
            push_model_eval(v2_version, precision, recall, f1_score(precision, recall))
        except Exception as exc:
            print(f"[retrain] WARNING: metric push skipped: {exc}")

        if precision < precision_threshold:
            client.set_registered_model_alias(MODEL_NAME, "archived", v2_version)
            client.set_registered_model_alias(MODEL_NAME, "production", v1_version)
            append_audit(
                "auto_rollback_v2_to_v1",
                demoted_version=v2_version,
                restored_version=v1_version,
                trigger_precision=precision,
                cycle=cycle,
            )
            reload_serve(serve_url)
            try:
                push_event("auto_rollback_v2_to_v1", v2_version)
                push_active_version(v1_version, "production")
                push_active_version(v2_version, "archived")
            except Exception as exc:
                print(f"[retrain] WARNING: metric push skipped: {exc}")
            print(f"Rollback complete. v{v1_version} restored to @production. v{v2_version} → @archived")
            return

    append_audit("post_deploy_stable", version=v2_version, cycles=cycles)
    print(f"[retrain] v{v2_version} passed {cycles} post-deploy cycles.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrain and promote after drift")
    parser.add_argument("--reference", default="data-pack/data/baseline.csv")
    parser.add_argument("--current", default="data-pack/data/drifted.csv")
    parser.add_argument("--holdout", default="data-pack/data/holdout.csv")
    parser.add_argument("--post-deploy-eval")
    parser.add_argument("--threshold", type=float, default=0.15)
    parser.add_argument("--serve-url", default="http://localhost:8000")
    parser.add_argument("--contamination", type=float, default=0.03)
    parser.add_argument("--n-estimators", type=int, default=100)
    parser.add_argument("--auto-approve", action="store_true")
    args = parser.parse_args()

    mlflow.set_tracking_uri(tracking_uri())
    client = MlflowClient(tracking_uri=tracking_uri())
    reference_df = pd.read_csv(args.reference)
    current_df = pd.read_csv(args.current)

    append_audit("drift_check_started", reference=args.reference, current=args.current)
    drift_result = detect_drift(reference_df, current_df, threshold=args.threshold, report_label="retrain")
    log_to_mlflow(drift_result)
    print(f"[retrain] Drift score: {drift_result.score:.4f}")
    print(f"[retrain] Drift detected: {drift_result.is_drift}")

    if not drift_result.is_drift:
        append_audit("no_drift_detected", drift_score=drift_result.score)
        print("[retrain] No drift detected. Retrain skipped.")
        return

    append_audit("drift_detected", drift_score=drift_result.score, threshold=args.threshold)
    append_audit("retrain_started")
    training_df = pd.concat([reference_df, current_df], ignore_index=True)
    model, anomaly_rate, training_rows = train_model(training_df, args.contamination, args.n_estimators)
    print(f"[retrain] Sliding-window rows: {training_rows}")
    print(f"[retrain] New model anomaly rate: {anomaly_rate:.4f}")

    holdout_df = pd.read_csv(args.holdout)
    v2_precision, v2_recall = evaluate_model(model, holdout_df)
    print(f"Holdout validation — v2 precision: {v2_precision:.4f}  recall: {v2_recall:.4f}")
    append_audit("holdout_validation", v2_precision=v2_precision, v2_recall=v2_recall)

    try:
        production_model = load_mlflow_model("production")
        v1_precision, v1_recall = evaluate_model(production_model, holdout_df)
        print(f"[retrain] Holdout validation — v1 precision: {v1_precision:.4f}  recall: {v1_recall:.4f}")
        append_audit("holdout_baseline", v1_precision=v1_precision, v1_recall=v1_recall)
        if v2_precision < v1_precision:
            print("[retrain] WARNING: v2 precision is below v1 on holdout.")
    except Exception as exc:
        print(f"[retrain] WARNING: could not evaluate v1 holdout: {exc}")

    staging_version = register_staging_model(
        model=model,
        training_rows=training_rows,
        anomaly_rate=anomaly_rate,
        drift_score=drift_result.score,
        input_example=feature_frame(training_df),
    )

    try:
        previous_production_version = client.get_model_version_by_alias(MODEL_NAME, "production").version
    except Exception:
        previous_production_version = "1"

    prompt = f"Drift detected. Model v{staging_version} registered as staging. Promote to production? [y/N] "
    append_audit("approval_requested", staging_version=staging_version)
    approved = args.auto_approve or input(prompt).strip().lower() == "y"

    if not approved:
        append_audit("promotion_rejected", staging_version=staging_version)
        print(f"[retrain] Promotion rejected. v{staging_version} remains @staging.")
        return

    promote(staging_version, previous_production_version, args.serve_url)
    if args.post_deploy_eval:
        post_deploy_monitor(
            v2_version=staging_version,
            v1_version=previous_production_version,
            eval_path=args.post_deploy_eval,
            serve_url=args.serve_url,
        )


if __name__ == "__main__":
    main()
