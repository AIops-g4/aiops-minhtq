#!/usr/bin/env python3
"""Streaming anomaly detection pipeline for the AIOps W1 individual lab."""

import argparse
import json
import math
import threading
from collections import defaultdict, deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


METRIC_NAMES = (
    "memory_usage_bytes",
    "memory_limit_bytes",
    "cpu_usage_percent",
    "http_requests_per_sec",
    "http_p99_latency_ms",
    "http_5xx_rate",
    "jvm_gc_pause_ms_avg",
    "queue_depth",
    "upstream_timeout_rate",
)

LOG_PATTERNS = {
    "memory_leak": ("gc pause exceeded threshold", "outofmemorywarning"),
    "traffic_spike": ("queue depth high", "server overloaded"),
    "dependency_timeout": ("upstream timeout rate", "circuit breaker open"),
}


class StreamingDetector:
    """Classify the generator's three fault types from streaming observations."""

    def __init__(self, warmup_samples=20, persistence_samples=3, history_size=20):
        self.warmup_samples = warmup_samples
        self.persistence_samples = persistence_samples
        self.history = deque(maxlen=history_size)
        self.ewma = {}
        self.counts = defaultdict(int)
        self.alerted_types = set()
        self.samples_seen = 0
        self.lock = threading.Lock()

    @staticmethod
    def _memory_slope(history):
        """Return least-squares memory growth in bytes per sample."""
        values = [row["memory_usage_bytes"] for row in history]
        n = len(values)
        if n < 8:
            return 0.0
        x_mean = (n - 1) / 2
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        return sum((i - x_mean) * value for i, value in enumerate(values)) / denominator

    @staticmethod
    def _log_evidence(logs):
        messages = " ".join(str(log.get("message", "")).lower() for log in logs)
        return {
            fault_type: any(pattern in messages for pattern in patterns)
            for fault_type, patterns in LOG_PATTERNS.items()
        }

    def _update_ewma(self, metrics):
        alpha = 0.08
        for name in METRIC_NAMES:
            value = float(metrics[name])
            previous = self.ewma.get(name, value)
            self.ewma[name] = alpha * value + (1 - alpha) * previous

    def process(self, payload):
        with self.lock:
            return self._process(payload)

    def _process(self, payload):
        metrics = payload["metrics"]
        logs = payload.get("logs", [])
        self.samples_seen += 1
        self.history.append(metrics)

        if self.samples_seen <= self.warmup_samples:
            self._update_ewma(metrics)
            return None

        evidence = self._log_evidence(logs)
        memory_util = metrics["memory_usage_bytes"] / metrics["memory_limit_bytes"] * 100
        memory_slope = self._memory_slope(self.history)
        baseline_rps = max(self.ewma.get("http_requests_per_sec", 1), 1)
        rps_ratio = metrics["http_requests_per_sec"] / baseline_rps

        candidates = {
            "dependency_timeout": (
                metrics["upstream_timeout_rate"] > 8
                and metrics["http_5xx_rate"] > 4
                and metrics["http_p99_latency_ms"] > 200
            ) or (
                evidence["dependency_timeout"]
                and metrics["upstream_timeout_rate"] > 5
            ),
            "memory_leak": (
                memory_util > 48
                and memory_slope > 1_500_000
                and metrics["jvm_gc_pause_ms_avg"] > 30
            ) or (
                evidence["memory_leak"]
                and memory_util > 50
                and metrics["jvm_gc_pause_ms_avg"] > 40
            ),
            "traffic_spike": (
                rps_ratio > 2
                and metrics["http_requests_per_sec"] > 250
                and metrics["queue_depth"] > 40
                and metrics["http_p99_latency_ms"] > 250
                and metrics["upstream_timeout_rate"] < 8
            ) or (
                evidence["traffic_spike"]
                and metrics["queue_depth"] > 40
                and metrics["upstream_timeout_rate"] < 8
            ),
        }

        # Do not let an active incident immediately redefine its own baseline.
        if not any(candidates.values()):
            self._update_ewma(metrics)

        for fault_type, active in candidates.items():
            self.counts[fault_type] = self.counts[fault_type] + 1 if active else 0

        # Priority prevents timeout-driven retries from being labeled traffic spike.
        for fault_type in ("dependency_timeout", "memory_leak", "traffic_spike"):
            if (
                self.counts[fault_type] >= self.persistence_samples
                and fault_type not in self.alerted_types
            ):
                self.alerted_types.add(fault_type)
                return self._build_alert(payload["timestamp"], fault_type, metrics, memory_util)
        return None

    @staticmethod
    def _build_alert(timestamp, fault_type, metrics, memory_util):
        if fault_type == "memory_leak":
            severity = "critical" if memory_util >= 80 else "warning"
            message = (
                f"Memory utilization is {memory_util:.1f}% with "
                f"GC pause {metrics['jvm_gc_pause_ms_avg']:.1f} ms"
            )
        elif fault_type == "traffic_spike":
            severity = "critical" if metrics["http_5xx_rate"] >= 10 else "warning"
            message = (
                f"Traffic is {metrics['http_requests_per_sec']:.1f} req/s, "
                f"queue depth {metrics['queue_depth']}, "
                f"P99 latency {metrics['http_p99_latency_ms']:.1f} ms"
            )
        else:
            severity = "critical" if metrics["upstream_timeout_rate"] >= 40 else "warning"
            message = (
                f"Upstream timeout rate is {metrics['upstream_timeout_rate']:.1f}% "
                f"with HTTP 5xx rate {metrics['http_5xx_rate']:.1f}%"
            )
        return {
            "timestamp": timestamp,
            "type": fault_type,
            "severity": severity,
            "message": message,
        }


class AlertWriter:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()

    def append(self, alert):
        line = json.dumps(alert, ensure_ascii=False)
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as output:
                output.write(line + "\n")


def validate_payload(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("metrics"), dict):
        raise ValueError("payload must contain a metrics object")
    if not isinstance(payload.get("logs", []), list):
        raise ValueError("logs must be an array")
    if not isinstance(payload.get("timestamp"), str):
        raise ValueError("timestamp must be an ISO 8601 string")
    try:
        datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp must be an ISO 8601 string") from exc
    if any(not isinstance(log, dict) for log in payload.get("logs", [])):
        raise ValueError("each log entry must be an object")
    for name in METRIC_NAMES:
        value = payload["metrics"].get(name)
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"metric {name} must be a finite number")
    if payload["metrics"]["memory_limit_bytes"] <= 0:
        raise ValueError("memory_limit_bytes must be positive")


def make_handler(detector, writer):
    class IngestHandler(BaseHTTPRequestHandler):
        def _json_response(self, status, body):
            encoded = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_POST(self):
            if self.path != "/ingest":
                self._json_response(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length))
                validate_payload(payload)
                alert = detector.process(payload)
                if alert:
                    writer.append(alert)
                    print(f"[ALERT] {json.dumps(alert)}", flush=True)
                self._json_response(200, {"status": "ok", "alert": alert})
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self._json_response(400, {"error": str(exc)})
            except Exception as exc:
                print(f"[ERROR] ingest failed: {exc}", flush=True)
                self._json_response(500, {"error": "internal server error"})

        def log_message(self, fmt, *args):
            return

    return IngestHandler


def main():
    parser = argparse.ArgumentParser(description="AIOps streaming anomaly pipeline")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--alerts-file",
        default=str(Path(__file__).with_name("alerts.jsonl")),
        help="JSONL output path",
    )
    parser.add_argument(
        "--reset-alerts",
        action="store_true",
        help="Clear the alerts file before starting",
    )
    args = parser.parse_args()

    writer = AlertWriter(args.alerts_file)
    if args.reset_alerts:
        writer.path.parent.mkdir(parents=True, exist_ok=True)
        writer.path.write_text("", encoding="utf-8")

    server = ThreadingHTTPServer((args.host, args.port), make_handler(StreamingDetector(), writer))
    print(f"[PIPELINE] Listening on http://{args.host}:{args.port}/ingest")
    print(f"[PIPELINE] Alerts file: {writer.path.resolve()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[PIPELINE] Stopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
