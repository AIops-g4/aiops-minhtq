"""Detection and triage layer for incident evidence candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any


SCHEMA_VERSION = "1.0"
SCORE_MEANING = "0..1, higher means more suspicious"


@dataclass(frozen=True)
class EvidenceCandidate:
    schema_version: str
    evidence_id: str
    evidence_type: str
    incident_id: str
    service: str
    detected_at: str
    timestamp_start: str
    timestamp_end: str
    score: float
    score_meaning: str
    summary: str
    signals: list[str]
    source_ref: dict[str, Any]
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        candidate = asdict(self)
        candidate["score"] = round(_clamp01(candidate["score"]), 4)
        return candidate


def load_incident(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Incident file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def detect_incident(incident: dict[str, Any], source_file: str = "") -> dict[str, Any]:
    incident_id = _short_incident_id(incident.get("incident_id", "unknown"))
    detected_at = str(incident["detected_at"])
    metric_candidates = detect_metric_anomalies(
        incident,
        incident_id,
        source_file,
        detected_at,
    )
    metric_services = {
        candidate.service
        for candidate in metric_candidates
        if candidate.score >= 0.55
    }
    log_candidates = detect_log_anomalies(
        incident,
        incident_id,
        source_file,
        metric_services,
        detected_at,
    )
    candidates = [*metric_candidates, *log_candidates]
    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    return {
        "schema_version": SCHEMA_VERSION,
        "incident_id": incident_id,
        "evidence_candidates": [candidate.to_dict() for candidate in candidates],
    }


def detect_metric_anomalies(
    incident: dict[str, Any],
    incident_id: str,
    source_file: str,
    detected_at_value: str,
) -> list[EvidenceCandidate]:
    detected_at = _parse_ts(detected_at_value)
    samples_by_key = incident.get("metrics_window", {}).get("samples", {})
    candidates: list[EvidenceCandidate] = []

    for series_key, raw_samples in samples_by_key.items():
        service, metric = _split_metric_key(series_key)
        samples = sorted(
            (_parse_ts(ts), float(value), ts)
            for ts, value in raw_samples
            if value is not None
        )
        if len(samples) < 6:
            continue

        pre = [value for ts, value, _ in samples if ts < detected_at]
        post = [value for ts, value, _ in samples if ts >= detected_at]
        if len(pre) < 4:
            split_at = max(2, int(len(samples) * 0.3))
            pre = [value for _, value, _ in samples[:split_at]]
            post = [value for _, value, _ in samples[split_at:]]
        if len(pre) < 2 or len(post) < 2:
            continue

        baseline_mean = mean(pre)
        baseline_std = pstdev(pre) or 1e-9
        baseline_median = median(pre)
        baseline_mad = median([abs(value - baseline_median) for value in pre]) or 1e-9
        post_mean = mean(post)
        post_peak = max(post)
        post_low = min(post)
        end_value = samples[-1][1]
        start_value = samples[0][1]
        absolute_delta = end_value - baseline_mean
        ratio = _safe_ratio(end_value, baseline_mean)
        peak_z = (post_peak - baseline_mean) / baseline_std
        low_z = (post_low - baseline_mean) / baseline_std
        robust_z = (end_value - baseline_median) / (1.4826 * baseline_mad)
        slope = (samples[-1][1] - samples[0][1]) / max(1, len(samples) - 1)

        worsening_direction = _metric_worsens_up(metric)
        directional_z = peak_z if worsening_direction else abs(low_z)
        drift = abs(post_mean - baseline_mean) / baseline_std
        ratio_signal = abs(ratio - 1.0)
        slope_signal = abs(slope) / (abs(baseline_mean) + 1e-9)
        raw_score = max(
            min(abs(directional_z) / 8.0, 1.0),
            min(abs(robust_z) / 10.0, 1.0),
            min(drift / 6.0, 1.0),
            min(ratio_signal / 2.5, 1.0),
            min(slope_signal * 20.0, 1.0),
        )
        if _is_operational_metric(metric):
            raw_score += 0.12
        score = _clamp01(raw_score)
        if score < 0.35:
            continue

        direction = "increased" if absolute_delta >= 0 else "decreased"
        signals = _metric_signals(metric, direction)
        signals.append("post_alert")
        candidates.append(
            EvidenceCandidate(
                schema_version=SCHEMA_VERSION,
                evidence_id=f"metric:{incident_id}:{series_key}",
                evidence_type="metric",
                incident_id=incident_id,
                service=service,
                detected_at=detected_at_value,
                timestamp_start=samples[0][2],
                timestamp_end=samples[-1][2],
                score=score,
                score_meaning=SCORE_MEANING,
                summary=f"{service} {metric} {direction} after alert",
                signals=signals,
                source_ref={
                    "system": "incident_json",
                    "file": source_file,
                    "path": f"metrics_window.samples.{series_key}",
                },
                details={
                    "metric": metric,
                    "baseline_mean": round(baseline_mean, 4),
                    "baseline_std": round(baseline_std, 4),
                    "baseline_median": round(baseline_median, 4),
                    "baseline_mad": round(baseline_mad, 4),
                    "post_mean": round(post_mean, 4),
                    "start_value": start_value,
                    "end_value": end_value,
                    "min_value": min(value for _, value, _ in samples),
                    "max_value": max(value for _, value, _ in samples),
                    "absolute_delta": round(absolute_delta, 4),
                    "ratio": round(ratio, 4),
                    "slope": round(slope, 6),
                    "post_alert_peak_z": round(peak_z, 4),
                    "post_alert_low_z": round(low_z, 4),
                    "robust_z": round(robust_z, 4),
                },
            )
        )

    return candidates


def detect_log_anomalies(
    incident: dict[str, Any],
    incident_id: str,
    source_file: str,
    metric_services: set[str],
    detected_at: str,
) -> list[EvidenceCandidate]:
    groups: dict[tuple[str, str, str], list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for index, log in enumerate(incident.get("logs", [])):
        template = normalize_log_message(str(log.get("msg", "")))
        key = (str(log.get("svc", "unknown")), str(log.get("level", "INFO")).upper(), template)
        groups[key].append((index, log))

    candidates: list[EvidenceCandidate] = []
    total_logs = max(1, len(incident.get("logs", [])))
    for (service, level, template), rows in groups.items():
        count = len(rows)
        severity_score = {"ERROR": 1.0, "WARN": 0.6, "INFO": 0.2}.get(level, 0.3)
        frequency_score = min(1.0, math.log1p(count) / math.log1p(max(3, total_logs * 0.15)))
        first_seen = min(str(log.get("ts")) for _, log in rows)
        last_seen = max(str(log.get("ts")) for _, log in rows)
        burst_score = _burst_score([str(log.get("ts")) for _, log in rows])
        keyword_score, keyword_signals = _keyword_score(template)
        metric_link_score = 1.0 if service in metric_services else 0.0
        score = (
            0.25 * severity_score
            + 0.20 * frequency_score
            + 0.20 * burst_score
            + 0.25 * keyword_score
            + 0.10 * metric_link_score
        )
        if score < 0.28:
            continue

        signals = ["log_template", f"log_level_{level.lower()}"]
        signals.extend(keyword_signals)
        if metric_link_score:
            signals.append("metric_linked")
        candidates.append(
            EvidenceCandidate(
                schema_version=SCHEMA_VERSION,
                evidence_id=f"log:{incident_id}:{service}:{_stable_id(level + template)}",
                evidence_type="log",
                incident_id=incident_id,
                service=service,
                detected_at=detected_at,
                timestamp_start=first_seen,
                timestamp_end=last_seen,
                score=_clamp01(score),
                score_meaning=SCORE_MEANING,
                summary=f"{service} emitted {count} {level} logs matching: {template}",
                signals=signals,
                source_ref={
                    "system": "incident_json",
                    "file": source_file,
                    "path": "logs",
                },
                details={
                    "template_id": _stable_id(template),
                    "template": template,
                    "svc": service,
                    "level": level,
                    "count": count,
                    "first_seen": first_seen,
                    "last_seen": last_seen,
                    "burst_score": round(burst_score, 4),
                    "keyword_score": keyword_score,
                    "metric_link_score": metric_link_score,
                    "raw_indices": [index for index, _ in rows[:25]],
                    "raw_examples": [log.get("msg") for _, log in rows[:3]],
                },
            )
        )

    return candidates


def normalize_log_message(message: str) -> str:
    normalized = message.strip()
    normalized = re.sub(r"\b\d+(?:\.\d+)?\s*(?:ms|s|sec|secs|seconds)\b", "<duration>", normalized, flags=re.I)
    normalized = re.sub(r"\b\d+(?:\.\d+)?%", "<percent>", normalized)
    normalized = re.sub(r"\bv\d+(?:\.\d+)+\b", "<version>", normalized, flags=re.I)
    normalized = re.sub(
        r"\b((?:order|product|attempt|revision|rev|request|trace|span|cn|pod)_?id)=[\w.-]+\b",
        r"\1=<id>",
        normalized,
        flags=re.I,
    )
    normalized = re.sub(r"\b(?:attempt|revision|rev|after_ms|waited|notAfter|tls_handshake_failures|utilization)=?[\w:.-]+\b", lambda m: _normalize_key_value(m.group(0)), normalized, flags=re.I)
    normalized = re.sub(r"(?<=path=)/[^\s]+|/[A-Za-z0-9_./-]+", "<path>", normalized)
    normalized = re.sub(r"\b\d+(?:\.\d+)?\b", "<num>", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _normalize_key_value(token: str) -> str:
    key = token.split("=", 1)[0] if "=" in token else token
    if "after_ms" in key or "waited" in key:
        return f"{key}=<duration>"
    if "utilization" in key:
        return f"{key}=<percent>"
    return f"{key}=<id>"


def _split_metric_key(series_key: str) -> tuple[str, str]:
    if "." not in series_key:
        return "unknown", series_key
    return tuple(series_key.split(".", 1))  # type: ignore[return-value]


def _metric_worsens_up(metric: str) -> bool:
    return not any(token in metric.lower() for token in ("free", "available", "success"))


def _is_operational_metric(metric: str) -> bool:
    tokens = ("latency", "error", "memory", "gc", "pool", "lag", "tls", "dns", "throttle", "cpu")
    return any(token in metric.lower() for token in tokens)


def _metric_signals(metric: str, direction: str) -> list[str]:
    lower = metric.lower()
    signals = ["metric_increase" if direction == "increased" else "metric_decrease"]
    for token, signal in (
        ("latency", "latency_anomaly"),
        ("error", "error_rate_anomaly"),
        ("memory", "memory_anomaly"),
        ("gc", "memory_anomaly"),
        ("pool", "pool_anomaly"),
        ("lag", "replication_lag_anomaly"),
        ("tls", "tls_anomaly"),
        ("dns", "dns_anomaly"),
        ("throttle", "throttling_anomaly"),
    ):
        if token in lower:
            signals.append(signal)
    signals.append("metric_spike")
    return signals


def _keyword_score(template: str) -> tuple[float, list[str]]:
    lower = template.lower()
    mapping = {
        "pool": "pool_anomaly",
        "connectionpool": "pool_anomaly",
        "timeout": "timeout_anomaly",
        "outofmemory": "memory_anomaly",
        "oom": "memory_anomaly",
        "tls": "tls_anomaly",
        "x509": "tls_anomaly",
        "certificate": "tls_anomaly",
        "dns": "dns_anomaly",
        "nxdomain": "dns_anomaly",
        "throttl": "throttling_anomaly",
        "replica lag": "replication_lag_anomaly",
        "lag": "replication_lag_anomaly",
        "exhausted": "pool_anomaly",
    }
    signals = sorted({signal for token, signal in mapping.items() if token in lower})
    if not signals:
        return 0.0, []
    return min(1.0, 0.45 + 0.2 * len(signals)), signals


def _burst_score(timestamps: list[str]) -> float:
    if len(timestamps) <= 1:
        return 0.0
    parsed = sorted(_parse_ts(ts) for ts in timestamps)
    span_seconds = max(1.0, (parsed[-1] - parsed[0]).total_seconds())
    per_minute = len(parsed) / (span_seconds / 60.0)
    return min(1.0, per_minute / 8.0)


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _safe_ratio(numerator: float, denominator: float) -> float:
    if abs(denominator) < 1e-9:
        return 1.0 if abs(numerator) < 1e-9 else 99.0
    return numerator / denominator


def _short_incident_id(incident_id: str) -> str:
    match = re.match(r"^(E\d+)", incident_id)
    return match.group(1) if match else incident_id


def _clamp01(value: float) -> float:
    if math.isnan(value) or math.isinf(value):
        return 0.0
    return max(0.0, min(1.0, value))


def _stable_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--incident", required=True)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    incident_path = Path(args.incident)
    incident = load_incident(incident_path)
    detection = detect_incident(incident, source_file=incident_path.as_posix())
    payload = json.dumps(detection, indent=2)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
