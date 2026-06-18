"""Best-effort Prometheus Pushgateway helpers for the MLOps lifecycle lab."""

from __future__ import annotations

import os

from prometheus_client import CollectorRegistry, Counter, Gauge, push_to_gateway

PUSHGATEWAY_URL = os.environ.get("PUSHGATEWAY_URL", "http://localhost:9091")


def _push(job: str, registry: CollectorRegistry) -> None:
    try:
        push_to_gateway(PUSHGATEWAY_URL, job=job, registry=registry)
    except Exception as exc:  # best-effort observability must not break the lab
        print(f"[metrics] WARNING: pushgateway unavailable: {exc}")


def push_drift_score(score: float, threshold: float) -> None:
    registry = CollectorRegistry()
    Gauge("mlops_drift_score", "Fraction of drifted features", registry=registry).set(score)
    Gauge("mlops_drift_threshold", "Configured drift threshold", registry=registry).set(threshold)
    Gauge("mlops_drift_is_drift", "1 if drift detected", registry=registry).set(
        1.0 if score > threshold else 0.0
    )
    _push("drift_detector", registry)


def push_model_eval(version: str, precision: float, recall: float, f1: float) -> None:
    registry = CollectorRegistry()
    labels = ["version"]
    Gauge("mlops_model_precision", "Model precision", labels, registry=registry).labels(version).set(precision)
    Gauge("mlops_model_recall", "Model recall", labels, registry=registry).labels(version).set(recall)
    Gauge("mlops_model_f1", "Model F1 score", labels, registry=registry).labels(version).set(f1)
    _push("retrain", registry)


def push_event(event_type: str, version: str) -> None:
    registry = CollectorRegistry()
    Counter(
        f"mlops_{event_type}_total",
        f"Total count of {event_type} events",
        ["version"],
        registry=registry,
    ).labels(version).inc()
    _push("retrain", registry)


def push_active_version(version: str, alias: str) -> None:
    registry = CollectorRegistry()
    Gauge(
        "mlops_active_version_number",
        "Integer version number for the alias",
        ["alias"],
        registry=registry,
    ).labels(alias).set(int(version) if str(version).isdigit() else 0)
    Gauge(
        "mlops_active_version_info",
        "Alias to version mapping",
        ["alias", "version"],
        registry=registry,
    ).labels(alias, str(version)).set(1)
    _push("retrain", registry)
