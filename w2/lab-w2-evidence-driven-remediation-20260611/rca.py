"""Root-cause ranking over correlated incident evidence."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

import networkx as nx

from correlation import correlate_incident, load_detection
from features import detect_incident, load_incident


SCHEMA_VERSION = "1.0"
DEFAULT_RANKER_WEIGHTS = {
    "pagerank": 0.40,
    "timestamp": 0.35,
    "causal_lag": 0.25,
}
DEGRADATION_Z = 3.0


@dataclass(frozen=True)
class RankerResult:
    name: str
    ranks: dict[str, int]
    scores: dict[str, float]
    signals: dict[str, list[str]]
    warnings: list[str]


@dataclass(frozen=True)
class MetricSeries:
    service: str
    metric: str
    timestamps: list[datetime]
    values: list[float]
    anomaly_values: list[float]
    degradation_time: datetime | None
    degradation_score: float


def rank_root_causes(
    incident: dict[str, Any],
    detection: dict[str, Any] | None = None,
    correlation: dict[str, Any] | None = None,
    source_file: str = "",
    rrf_k: int = 60,
    ranker_weights: dict[str, float] | None = None,
    max_lag_samples: int = 8,
    min_corr: float = 0.55,
) -> dict[str, Any]:
    """Rank likely root-cause services for each correlated alert cluster."""
    if detection is None:
        detection = detect_incident(incident, source_file=source_file)
    if correlation is None:
        correlation = correlate_incident(
            incident,
            detection=detection,
            source_file=source_file,
        )

    incident_id = _short_incident_id(
        str(detection.get("incident_id") or incident.get("incident_id", "unknown"))
    )
    weights = dict(DEFAULT_RANKER_WEIGHTS)
    if ranker_weights:
        weights.update(
            {
                name: float(value)
                for name, value in ranker_weights.items()
                if name in DEFAULT_RANKER_WEIGHTS
            }
        )

    candidates_by_service = _candidate_records_by_service(detection)
    metric_series_by_service = _metric_series_by_service(incident)
    graph = _build_directed_service_graph(incident)

    rankings: list[dict[str, Any]] = []
    for cluster in correlation.get("clusters", []):
        services = _cluster_services(cluster, candidates_by_service)
        rankings.append(
            _rank_cluster(
                cluster=cluster,
                services=services,
                candidates_by_service=candidates_by_service,
                metric_series_by_service=metric_series_by_service,
                graph=graph,
                rrf_k=rrf_k,
                ranker_weights=weights,
                max_lag_samples=max_lag_samples,
                min_corr=min_corr,
            )
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "incident_id": incident_id,
        "params": {
            "rrf_k": rrf_k,
            "ranker_weights": {
                name: round(weights[name], 4)
                for name in sorted(DEFAULT_RANKER_WEIGHTS)
            },
            "max_lag_samples": max_lag_samples,
            "min_corr": min_corr,
            "degradation_z": DEGRADATION_Z,
        },
        "root_cause_rankings": rankings,
    }


def load_correlation(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Correlation file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _rank_cluster(
    cluster: dict[str, Any],
    services: list[str],
    candidates_by_service: dict[str, list[dict[str, Any]]],
    metric_series_by_service: dict[str, list[MetricSeries]],
    graph: nx.DiGraph,
    rrf_k: int,
    ranker_weights: dict[str, float],
    max_lag_samples: int,
    min_corr: float,
) -> dict[str, Any]:
    warnings: list[str] = []
    if not services:
        warnings.append("no_candidate_services")
        return {
            "cluster_id": str(cluster.get("cluster_id", "")),
            "services": [],
            "active_rankers": [],
            "confidence": {"gap_ratio": 0.0, "level": "low"},
            "candidates": [],
            "warnings": warnings,
        }

    rankers = [
        _pagerank_ranker(services, graph),
        _timestamp_ranker(services, candidates_by_service, metric_series_by_service),
        _causal_lag_ranker(
            services,
            metric_series_by_service,
            max_lag_samples=max_lag_samples,
            min_corr=min_corr,
        ),
    ]
    active_rankers = [ranker for ranker in rankers if ranker.ranks]
    for ranker in rankers:
        warnings.extend(ranker.warnings)

    fused = _rrf_fuse(services, active_rankers, ranker_weights, rrf_k)
    if not fused:
        warnings.append("rrf_no_active_rankers")
        fused = {
            service: 1.0 / (rrf_k + rank)
            for rank, service in enumerate(sorted(services), start=1)
        }

    ordered = sorted(fused, key=lambda service: (-fused[service], service))
    top_score = fused[ordered[0]] if ordered else 0.0
    confidence = _confidence_gap([fused[service] for service in ordered])

    candidate_outputs: list[dict[str, Any]] = []
    for rank, service in enumerate(ordered, start=1):
        ranker_ranks = {
            ranker.name: ranker.ranks[service]
            for ranker in active_rankers
            if service in ranker.ranks
        }
        ranker_scores = {
            ranker.name: round(ranker.scores.get(service, 0.0), 6)
            for ranker in active_rankers
            if service in ranker.scores
        }
        explanation_signals = sorted(
            {
                signal
                for ranker in active_rankers
                for signal in ranker.signals.get(service, [])
            }
        )
        candidate_outputs.append(
            {
                "rank": rank,
                "service": service,
                "rrf_score": round(fused[service], 6),
                "normalized_score": round(_safe_ratio(fused[service], top_score), 4),
                "ranker_ranks": ranker_ranks,
                "ranker_scores": ranker_scores,
                "evidence_ids": _service_evidence_ids(service, candidates_by_service),
                "explanation_signals": explanation_signals,
            }
        )

    return {
        "cluster_id": str(cluster.get("cluster_id", "")),
        "services": services,
        "active_rankers": [ranker.name for ranker in active_rankers],
        "confidence": confidence,
        "candidates": candidate_outputs,
        "warnings": sorted(set(warnings)),
    }


def _pagerank_ranker(services: list[str], graph: nx.DiGraph) -> RankerResult:
    warnings: list[str] = []
    if not services:
        return RankerResult("pagerank", {}, {}, {}, ["pagerank_skipped_no_services"])

    work_graph = graph.copy()
    for service in services:
        work_graph.add_node(service)

    if work_graph.number_of_edges() == 0:
        warnings.append("pagerank_graph_has_no_edges")
        scores = {service: 1.0 for service in services}
    else:
        personalization = {
            node: (1.0 if node in services else 0.0)
            for node in work_graph.nodes
        }
        if sum(personalization.values()) == 0:
            personalization = None  # type: ignore[assignment]
        try:
            raw_scores = nx.pagerank(
                work_graph,
                alpha=0.85,
                personalization=personalization,
                dangling=personalization,
            )
        except nx.PowerIterationFailedConvergence:
            warnings.append("pagerank_failed_to_converge")
            raw_scores = {service: 1.0 for service in services}
        scores = {service: float(raw_scores.get(service, 0.0)) for service in services}

    ordered = sorted(services, key=lambda service: (-scores[service], service))
    return RankerResult(
        name="pagerank",
        ranks={service: rank for rank, service in enumerate(ordered, start=1)},
        scores=scores,
        signals={
            service: ["high_pagerank_downstream_dependency"]
            if rank == 1
            else ["pagerank_dependency_candidate"]
            for rank, service in enumerate(ordered, start=1)
        },
        warnings=warnings,
    )


def _timestamp_ranker(
    services: list[str],
    candidates_by_service: dict[str, list[dict[str, Any]]],
    metric_series_by_service: dict[str, list[MetricSeries]],
) -> RankerResult:
    if not services:
        return RankerResult("timestamp", {}, {}, {}, ["timestamp_skipped_no_services"])

    entries: list[tuple[datetime, float, str, str]] = []
    warnings: list[str] = []
    for service in services:
        series = metric_series_by_service.get(service, [])
        degraded = [item for item in series if item.degradation_time is not None]
        if degraded:
            best = min(
                degraded,
                key=lambda item: (
                    item.degradation_time or datetime.max.replace(tzinfo=timezone.utc),
                    -item.degradation_score,
                    item.metric,
                ),
            )
            entries.append(
                (
                    best.degradation_time or datetime.max.replace(tzinfo=timezone.utc),
                    best.degradation_score,
                    service,
                    "earliest_metric_degradation",
                )
            )
            continue

        evidence_time = _earliest_evidence_time(candidates_by_service.get(service, []))
        if evidence_time is not None:
            entries.append((evidence_time, 0.0, service, "earliest_evidence_fallback"))
        else:
            warnings.append(f"timestamp_missing_evidence:{service}")
            entries.append(
                (
                    datetime.max.replace(tzinfo=timezone.utc),
                    0.0,
                    service,
                    "timestamp_missing_evidence",
                )
            )

    entries.sort(key=lambda item: (item[0], -item[1], item[2]))
    ranks = {service: rank for rank, (_, _, service, _) in enumerate(entries, start=1)}
    if len(entries) <= 1:
        scores = {entries[0][2]: 1.0} if entries else {}
    else:
        min_time = min(item[0] for item in entries)
        max_time = max(item[0] for item in entries)
        span = max(1.0, (max_time - min_time).total_seconds())
        scores = {
            service: 1.0 - ((timestamp - min_time).total_seconds() / span)
            if timestamp != datetime.max.replace(tzinfo=timezone.utc)
            else 0.0
            for timestamp, _, service, _ in entries
        }
    signals = {service: [signal] for _, _, service, signal in entries}
    return RankerResult("timestamp", ranks, scores, signals, warnings)


def _causal_lag_ranker(
    services: list[str],
    metric_series_by_service: dict[str, list[MetricSeries]],
    max_lag_samples: int,
    min_corr: float,
) -> RankerResult:
    service_series = {
        service: _representative_anomaly_series(metric_series_by_service.get(service, []))
        for service in services
    }
    service_series = {
        service: values
        for service, values in service_series.items()
        if values and len(values) >= (max_lag_samples * 2 + 3)
    }
    if len(service_series) < 2:
        return RankerResult(
            "causal_lag",
            {},
            {},
            {},
            ["causal_lag_skipped_insufficient_metric_series"],
        )

    scores = {service: 0.0 for service in service_series}
    wins = {service: 0 for service in service_series}
    for index, service_a in enumerate(sorted(service_series)):
        for service_b in sorted(service_series)[index + 1 :]:
            lag, corr = _best_lag(
                service_series[service_a],
                service_series[service_b],
                max_lag_samples,
            )
            if abs(corr) < min_corr or lag == 0:
                continue
            if lag > 0:
                leader = service_a
            else:
                leader = service_b
            scores[leader] += abs(corr)
            wins[leader] += 1

    if not any(score > 0 for score in scores.values()):
        return RankerResult(
            "causal_lag",
            {},
            {},
            {},
            ["causal_lag_skipped_inconclusive_correlations"],
        )

    ordered = sorted(scores, key=lambda service: (-scores[service], service))
    return RankerResult(
        name="causal_lag",
        ranks={service: rank for rank, service in enumerate(ordered, start=1)},
        scores=scores,
        signals={
            service: ["metric_leads_related_service"]
            if wins.get(service, 0) > 0
            else ["causal_lag_no_directional_win"]
            for service in scores
        },
        warnings=[],
    )


def _rrf_fuse(
    services: list[str],
    rankers: list[RankerResult],
    ranker_weights: dict[str, float],
    rrf_k: int,
) -> dict[str, float]:
    fused = {service: 0.0 for service in services}
    for ranker in rankers:
        weight = ranker_weights.get(ranker.name, 0.0)
        if weight <= 0:
            continue
        for service, rank in ranker.ranks.items():
            if service in fused:
                fused[service] += weight / (rrf_k + rank)
    return fused


def _candidate_records_by_service(
    detection: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    records: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in detection.get("evidence_candidates", []):
        service = str(candidate.get("service", ""))
        if service:
            records[service].append(candidate)
    for service in records:
        records[service].sort(
            key=lambda item: (
                str(item.get("timestamp_start", "")),
                -float(item.get("score", 0.0) or 0.0),
                str(item.get("evidence_id", "")),
            )
        )
    return records


def _cluster_services(
    cluster: dict[str, Any],
    candidates_by_service: dict[str, list[dict[str, Any]]],
) -> list[str]:
    services = {str(service) for service in cluster.get("services", []) if service}
    if services:
        return sorted(services)

    evidence_ids = {str(evidence_id) for evidence_id in cluster.get("evidence_ids", [])}
    for service, candidates in candidates_by_service.items():
        if any(str(candidate.get("evidence_id", "")) in evidence_ids for candidate in candidates):
            services.add(service)
    return sorted(services)


def _build_directed_service_graph(incident: dict[str, Any]) -> nx.DiGraph:
    graph = nx.DiGraph()
    for node in incident.get("topology", {}).get("nodes", []):
        node_id = str(node.get("id", ""))
        if node_id:
            graph.add_node(node_id)
    for edge in incident.get("topology", {}).get("edges", []):
        source = str(edge.get("from", ""))
        target = str(edge.get("to", ""))
        if source and target:
            graph.add_edge(source, target)
    for trace in incident.get("traces", []):
        source = str(trace.get("from", ""))
        target = str(trace.get("to", ""))
        if source and target:
            graph.add_edge(source, target)
    return graph


def _metric_series_by_service(incident: dict[str, Any]) -> dict[str, list[MetricSeries]]:
    detected_at = _parse_ts(str(incident.get("detected_at", "")))
    by_service: dict[str, list[MetricSeries]] = defaultdict(list)
    for series_key, raw_samples in incident.get("metrics_window", {}).get("samples", {}).items():
        service, metric = _split_metric_key(str(series_key))
        samples = sorted(
            (_parse_ts(str(ts)), float(value))
            for ts, value in raw_samples
            if value is not None
        )
        if len(samples) < 6:
            continue
        timestamps = [timestamp for timestamp, _ in samples]
        values = [value for _, value in samples]
        pre_values = [value for timestamp, value in samples if timestamp < detected_at]
        if len(pre_values) < 4:
            split_at = max(2, int(len(values) * 0.3))
            pre_values = values[:split_at]
        if len(pre_values) < 2:
            continue
        baseline_mean = mean(pre_values)
        baseline_std = pstdev(pre_values) or 1e-9
        worsens_up = _metric_worsens_up(metric)
        anomaly_values = [
            _directional_z(value, baseline_mean, baseline_std, worsens_up)
            for value in values
        ]
        degradation_time = None
        degradation_score = 0.0
        for timestamp, anomaly_value in zip(timestamps, anomaly_values, strict=True):
            if anomaly_value >= DEGRADATION_Z:
                degradation_time = timestamp
                degradation_score = anomaly_value
                break
        by_service[service].append(
            MetricSeries(
                service=service,
                metric=metric,
                timestamps=timestamps,
                values=values,
                anomaly_values=anomaly_values,
                degradation_time=degradation_time,
                degradation_score=degradation_score,
            )
        )
    return by_service


def _representative_anomaly_series(series: list[MetricSeries]) -> list[float]:
    if not series:
        return []
    degraded = [item for item in series if item.degradation_time is not None]
    pool = degraded or series
    best = max(
        pool,
        key=lambda item: (
            item.degradation_score,
            max(item.anomaly_values) if item.anomaly_values else 0.0,
            item.metric,
        ),
    )
    return best.anomaly_values


def _best_lag(values_a: list[float], values_b: list[float], max_lag_samples: int) -> tuple[int, float]:
    best_lag = 0
    best_corr = 0.0
    for lag in range(-max_lag_samples, max_lag_samples + 1):
        if lag > 0:
            segment_a = values_a[:-lag]
            segment_b = values_b[lag:]
        elif lag < 0:
            segment_a = values_a[-lag:]
            segment_b = values_b[:lag]
        else:
            segment_a = values_a
            segment_b = values_b
        if len(segment_a) < 3 or len(segment_b) < 3:
            continue
        corr = _pearson(segment_a, segment_b)
        if abs(corr) > abs(best_corr) or (
            abs(corr) == abs(best_corr) and abs(lag) < abs(best_lag)
        ):
            best_lag = lag
            best_corr = corr
    return best_lag, best_corr


def _pearson(values_a: list[float], values_b: list[float]) -> float:
    if len(values_a) != len(values_b) or len(values_a) < 2:
        return 0.0
    mean_a = mean(values_a)
    mean_b = mean(values_b)
    centered_a = [value - mean_a for value in values_a]
    centered_b = [value - mean_b for value in values_b]
    denom_a = math.sqrt(sum(value * value for value in centered_a))
    denom_b = math.sqrt(sum(value * value for value in centered_b))
    if denom_a <= 1e-12 or denom_b <= 1e-12:
        return 0.0
    return sum(a * b for a, b in zip(centered_a, centered_b, strict=True)) / (
        denom_a * denom_b
    )


def _earliest_evidence_time(candidates: list[dict[str, Any]]) -> datetime | None:
    timestamps: list[datetime] = []
    for candidate in candidates:
        value = candidate.get("timestamp_start") or candidate.get("detected_at")
        if not value:
            continue
        try:
            timestamps.append(_parse_ts(str(value)))
        except ValueError:
            continue
    return min(timestamps) if timestamps else None


def _service_evidence_ids(
    service: str,
    candidates_by_service: dict[str, list[dict[str, Any]]],
) -> list[str]:
    return sorted(
        {
            str(candidate.get("evidence_id", ""))
            for candidate in candidates_by_service.get(service, [])
            if candidate.get("evidence_id")
        }
    )


def _confidence_gap(scores: list[float]) -> dict[str, Any]:
    if not scores:
        return {"gap_ratio": 0.0, "level": "low"}
    if len(scores) == 1:
        return {"gap_ratio": 1.0, "level": "high"}
    top = scores[0]
    second = scores[1]
    gap_ratio = _safe_ratio(top - second, top)
    if gap_ratio > 0.30:
        level = "high"
    elif gap_ratio >= 0.10:
        level = "medium"
    else:
        level = "low"
    return {"gap_ratio": round(gap_ratio, 4), "level": level}


def _directional_z(
    value: float,
    baseline_mean: float,
    baseline_std: float,
    worsens_up: bool,
) -> float:
    z = (value - baseline_mean) / baseline_std
    return z if worsens_up else -z


def _split_metric_key(series_key: str) -> tuple[str, str]:
    if "." not in series_key:
        return "unknown", series_key
    service, metric = series_key.split(".", 1)
    return service, metric


def _metric_worsens_up(metric: str) -> bool:
    return not any(token in metric.lower() for token in ("free", "available", "success"))


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )


def _short_incident_id(incident_id: str) -> str:
    match = re.match(r"^(E\d+)", incident_id)
    return match.group(1) if match else incident_id


def _safe_ratio(numerator: float, denominator: float) -> float:
    if abs(denominator) < 1e-12:
        return 0.0
    return numerator / denominator


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--incident", required=True)
    parser.add_argument("--evidence", default="")
    parser.add_argument("--correlation", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--max-lag-samples", type=int, default=8)
    parser.add_argument("--min-corr", type=float, default=0.55)
    args = parser.parse_args()

    incident_path = Path(args.incident)
    incident = load_incident(incident_path)
    detection = load_detection(Path(args.evidence)) if args.evidence else None
    correlation = load_correlation(Path(args.correlation)) if args.correlation else None
    rca = rank_root_causes(
        incident,
        detection=detection,
        correlation=correlation,
        source_file=incident_path.as_posix(),
        rrf_k=args.rrf_k,
        max_lag_samples=args.max_lag_samples,
        min_corr=args.min_corr,
    )
    payload = json.dumps(rca, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
