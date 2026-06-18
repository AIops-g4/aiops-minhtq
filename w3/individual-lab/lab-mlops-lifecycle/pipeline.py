"""Train and register an IsolationForest anomaly detector with MLflow."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import mlflow
import mlflow.sklearn
import pandas as pd
from mlflow import MlflowClient
from sklearn.ensemble import IsolationForest

EXPERIMENT_NAME = "anomaly-detection"
MODEL_NAME = "anomaly-detector"
FEATURES = ["latency_p99", "error_rate", "rps"]


def load_features(csv_path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    missing = [column for column in FEATURES if column not in df.columns]
    if missing:
        raise ValueError(f"Missing feature columns in {csv_path}: {missing}")
    return df[FEATURES].dropna()


def tracking_uri() -> str:
    return os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")


def train_and_register(
    data_path: str | Path,
    alias: str = "production",
    contamination: float = 0.03,
    n_estimators: int = 100,
    random_state: int = 42,
) -> str:
    uri = tracking_uri()
    mlflow.set_tracking_uri(uri)
    mlflow.set_experiment(EXPERIMENT_NAME)

    features = load_features(data_path)
    model = IsolationForest(
        contamination=contamination,
        n_estimators=n_estimators,
        random_state=random_state,
        n_jobs=-1,
    )
    model.fit(features)

    predictions = model.predict(features)
    anomaly_rate = float((predictions == -1).mean())

    with mlflow.start_run(run_name=f"train-{alias}") as run:
        mlflow.log_param("contamination", contamination)
        mlflow.log_param("n_estimators", n_estimators)
        mlflow.log_param("random_state", random_state)
        mlflow.log_param("training_rows", len(features))
        mlflow.log_param("features", ",".join(FEATURES))
        mlflow.log_metric("train_anomaly_rate", anomaly_rate)
        mlflow.log_metric("feature_count", len(FEATURES))
        mlflow.sklearn.log_model(
            sk_model=model,
            artifact_path="model",
            registered_model_name=MODEL_NAME,
            input_example=features.head(3),
        )
        print(f"[pipeline] Run ID: {run.info.run_id}")
        print(f"[pipeline] Anomaly rate: {anomaly_rate:.4f}")

    client = MlflowClient(tracking_uri=uri)
    versions = client.search_model_versions(f"name='{MODEL_NAME}'")
    latest = max(versions, key=lambda version: int(version.version))
    client.set_registered_model_alias(MODEL_NAME, alias, latest.version)
    print(f"[pipeline] Registered {MODEL_NAME} v{latest.version} -> @{alias}")
    return latest.version


def main() -> None:
    parser = argparse.ArgumentParser(description="Train anomaly detector")
    parser.add_argument("--data", default="data-pack/data/baseline.csv")
    parser.add_argument("--alias", default="production")
    parser.add_argument("--contamination", type=float, default=0.03)
    parser.add_argument("--n-estimators", type=int, default=100)
    parser.add_argument("--random-state", type=int, default=42)
    args = parser.parse_args()

    train_and_register(
        data_path=args.data,
        alias=args.alias,
        contamination=args.contamination,
        n_estimators=args.n_estimators,
        random_state=args.random_state,
    )


if __name__ == "__main__":
    main()
