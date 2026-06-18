"""Optional Prometheus metrics for the closed-loop orchestrator."""

from __future__ import annotations

try:
    from prometheus_client import Counter, Gauge, start_http_server
except ImportError:  # pragma: no cover - optional runtime dependency
    Counter = Gauge = None
    start_http_server = None


class _NoopMetric:
    def labels(self, **_: str) -> "_NoopMetric":
        return self

    def inc(self) -> None:
        return None

    def set(self, _: float) -> None:
        return None


if Counter and Gauge:
    action_counter = Counter(
        "closed_loop_actions_total",
        "Total closed-loop actions by outcome",
        ["service", "runbook", "outcome"],
    )
    circuit_breaker_gauge = Gauge(
        "closed_loop_circuit_breaker_state",
        "Circuit-breaker state per service (0=closed, 1=open)",
        ["service"],
    )
    blast_radius_gauge = Gauge(
        "closed_loop_blast_radius_remaining",
        "Remaining global actions in the current one-minute window",
        ["service"],
    )
    mutex_gauge = Gauge(
        "closed_loop_mutex_locked",
        "Per-service mutex state (0=free, 1=locked)",
        ["service"],
    )
    verify_status_gauge = Gauge(
        "closed_loop_verify_status",
        "Last verify state (0=fail, 1=pass, 2=in_progress)",
        ["service", "runbook"],
    )
else:
    action_counter = _NoopMetric()
    circuit_breaker_gauge = _NoopMetric()
    blast_radius_gauge = _NoopMetric()
    mutex_gauge = _NoopMetric()
    verify_status_gauge = _NoopMetric()


_started = False


def start_metrics_server(port: int = 9100) -> bool:
    """Start metrics HTTP server if prometheus_client is available."""
    global _started
    if _started or start_http_server is None:
        return False
    start_http_server(port)
    _started = True
    return True
