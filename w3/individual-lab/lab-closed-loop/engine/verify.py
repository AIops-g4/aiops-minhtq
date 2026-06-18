"""Prometheus-based verification for post-action recovery."""

from __future__ import annotations

import time
from typing import Any

import requests

from engine.logger import JsonLogger

log = JsonLogger()


def query_prometheus(prometheus_url: str, promql: str) -> float | None:
    try:
        response = requests.get(
            f"{prometheus_url}/api/v1/query",
            params={"query": promql},
            timeout=5,
        )
        response.raise_for_status()
        result = response.json().get("data", {}).get("result", [])
        if not result:
            return None
        return float(result[0]["value"][1])
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
        log.error(
            "PROMETHEUS_QUERY_ERROR",
            action="verify",
            result="error",
            query=promql,
            error=str(exc),
        )
        return None


def verify_service(
    prometheus_url: str,
    service: str,
    baseline: dict[str, Any],
) -> bool:
    thresholds = baseline["verify_thresholds"]
    queries = baseline["prometheus_queries"]
    timeout_s = int(thresholds["verify_timeout_seconds"])
    poll_interval_s = int(thresholds["verify_poll_interval_seconds"])
    min_samples = int(thresholds["verify_min_samples"])

    latency_q = queries["latency_p99"].replace("{service}", service)
    error_q = queries["error_rate_pct"].replace("{service}", service)
    up_q = queries["up"].replace("{service}", service)

    deadline = time.time() + timeout_s
    samples = 0
    consecutive_passes = 0

    log.info(
        "VERIFY_START",
        service=service,
        action="verify",
        result="started",
        timeout_s=timeout_s,
    )

    while time.time() < deadline:
        samples += 1
        latency = query_prometheus(prometheus_url, latency_q)
        error_rate = query_prometheus(prometheus_url, error_q)
        up = query_prometheus(prometheus_url, up_q)

        latency_ok = (
            latency is not None and latency <= thresholds["latency_p99_max_ms"]
        )
        error_ok = (
            error_rate is not None and error_rate <= thresholds["error_rate_max_pct"]
        )
        up_ok = up is not None and up >= thresholds["up_required"]

        log.info(
            "VERIFY_SAMPLE",
            service=service,
            action="verify",
            result="sampled",
            sample=samples,
            latency_p99_ms=latency,
            error_rate_pct=error_rate,
            up=up,
            latency_ok=latency_ok,
            error_ok=error_ok,
            up_ok=up_ok,
        )

        if latency_ok and error_ok and up_ok:
            consecutive_passes += 1
            if consecutive_passes >= min_samples:
                log.info(
                    "VERIFY_PASS",
                    service=service,
                    action="verify",
                    result="success",
                    samples=samples,
                )
                return True
        else:
            consecutive_passes = 0

        time.sleep(poll_interval_s)

    log.warning(
        "VERIFY_FAIL",
        service=service,
        action="verify",
        result="fail",
        samples=samples,
    )
    return False
