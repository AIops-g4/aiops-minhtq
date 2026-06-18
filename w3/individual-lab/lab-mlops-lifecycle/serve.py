"""FastAPI serving layer for the MLflow production alias."""

from __future__ import annotations

import argparse
import os
import time
from contextlib import asynccontextmanager
from typing import Any

import mlflow
import mlflow.sklearn
import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel

try:
    from pydantic import field_validator
except ImportError:  # Pydantic v1
    from pydantic import validator as field_validator

MODEL_NAME = "anomaly-detector"
MODEL_URI = f"models:/{MODEL_NAME}@production"
FEATURES = ["latency_p99", "error_rate", "rps"]

REQUESTS = Counter("serve_requests_total", "Total predict requests")
LATENCY = Histogram("serve_predict_latency_seconds", "Prediction latency")
ACTIVE_VERSION = Gauge("serve_active_version", "Loaded MLflow model version")

state: dict[str, Any] = {"model": None, "version": None, "model_uri": MODEL_URI}


def tracking_uri() -> str:
    return os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")


def load_production_model() -> None:
    uri = tracking_uri()
    mlflow.set_tracking_uri(uri)
    client = mlflow.MlflowClient(tracking_uri=uri)
    model_version = client.get_model_version_by_alias(MODEL_NAME, "production")
    state["model"] = mlflow.sklearn.load_model(MODEL_URI)
    state["version"] = str(model_version.version)
    state["model_uri"] = MODEL_URI
    if str(model_version.version).isdigit():
        ACTIVE_VERSION.set(int(model_version.version))
    print(f"[serve] Loaded {MODEL_NAME} v{model_version.version} from @production")


@asynccontextmanager
async def lifespan(_: FastAPI):
    load_production_model()
    yield
    state["model"] = None


app = FastAPI(title="Anomaly Detector API", lifespan=lifespan)


class PredictRequest(BaseModel):
    features: list[float] | list[list[float]]

    @field_validator("features")
    def validate_features(cls, value):
        if not value:
            raise ValueError("features must not be empty")
        first = value[0]
        if isinstance(first, list):
            for row in value:
                if len(row) != len(FEATURES):
                    raise ValueError(f"each row must contain {len(FEATURES)} features")
        elif len(value) != len(FEATURES):
            raise ValueError(f"features must contain {len(FEATURES)} values")
        return value


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/predict")
def predict(request: PredictRequest) -> dict[str, Any]:
    if state["model"] is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    raw_features = request.features
    if isinstance(raw_features[0], list):
        matrix = np.array(raw_features, dtype=float)
        single = False
    else:
        matrix = np.array([raw_features], dtype=float)
        single = True

    REQUESTS.inc()
    start = time.perf_counter()
    predictions = state["model"].predict(matrix).astype(int).tolist()
    scores = state["model"].score_samples(matrix).astype(float).tolist()
    LATENCY.observe(time.perf_counter() - start)

    if single:
        return {
            "prediction": predictions[0],
            "score": scores[0],
            "version": str(state["version"]),
        }
    return {
        "predictions": predictions,
        "scores": scores,
        "version": str(state["version"]),
    }


@app.get("/health/active-version")
def active_version() -> dict[str, str]:
    if state["model"] is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {
        "model_name": MODEL_NAME,
        "version": str(state["version"]),
        "alias": "production",
        "model_uri": str(state["model_uri"]),
    }


@app.post("/reload")
def reload_model() -> dict[str, str]:
    load_production_model()
    return {"status": "reloaded", "version": str(state["version"])}


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve anomaly detector API")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload-on-start", action="store_true")
    args = parser.parse_args()
    uvicorn.run("serve:app", host=args.host, port=args.port, reload=args.reload_on_start)


if __name__ == "__main__":
    main()
