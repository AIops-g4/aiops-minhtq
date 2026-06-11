"""Alert correlation layer over normalized evidence candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

import networkx as nx

from features import detect_incident, load_incident


SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class AlertRecord:
    evidence_id: str
    evidence_type: str
    incident_id: str
    service: str
    detected_at: str
    anchor_dt: datetime
    timestamp_start: str
    timestamp_end: str
    start_dt: datetime
    end_dt: datetime
    score: float
    summary: str
    signals: list[str]
    details: dict[str, Any]
    candidate: dict[str, Any]


def correlate_incident(
    incident: dict[str, Any],
    detection: dict[str, Any] | None = None,
    source_file: str = "",
    gap_sec: int = 300,
    max_hop: int = 2,
    min_score: float = 0.28,
) -> dict[str, Any]:
    """Group detection evidence by time session and service topology."""
    if detection is None:
        detection = detect_incident(incident, source_file=source_file)

    incident_id = _short_incident_id(
        str(detection.get("incident_id") or incident.get("incident_id", "unknown"))
    )
    records = _candidate_records(detection, incident_id, min_score)
    graph, trace_edges_added = _build_service_graph(incident, records)

    clusters: list[dict[str, Any]] = []
    for session_idx, session in enumerate(_session_groups(records, gap_sec), start=1):
        for group_idx, (group, topology_details) in enumerate(
            _topology_groups(session, graph, trace_edges_added, max_hop),
            start=1,
        ):
            cluster_id = f"corr:{incident_id}:s{session_idx:03d}:g{group_idx:03d}"
            clusters.append(_summarize_cluster(cluster_id, group, topology_details))

    clusters.sort(
        key=lambda cluster: (
            cluster["time_range"][0],
            -cluster["max_score"],
            cluster["cluster_id"],
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "incident_id": incident_id,
        "input_alerts": len(records),
        "output_clusters": len(clusters),
        "reduction_ratio": round(1 - len(clusters) / len(records), 4)
        if records
        else 0,
        "params": {
            "gap_sec": gap_sec,
            "max_hop": max_hop,
            "min_score": min_score,
            "time_anchor_field": "detected_at",
        },
        "clusters": clusters,
    }


def load_detection(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Detection file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _candidate_records(
    detection: dict[str, Any],
    incident_id: str,
    min_score: float,
) -> list[AlertRecord]:
    records: list[AlertRecord] = []
    for candidate in detection.get("evidence_candidates", []):
        score = _clamp01(float(candidate.get("score", 0.0)))
        if score < min_score:
            continue
        detected_at = str(candidate.get("detected_at") or "")
        timestamp_start = str(candidate.get("timestamp_start", ""))
        timestamp_end = str(candidate.get("timestamp_end") or timestamp_start)
        anchor_ts = detected_at or timestamp_start
        if not anchor_ts or not timestamp_start:
            continue
        try:
            anchor_dt = _parse_ts(anchor_ts)
            start_dt = _parse_ts(timestamp_start)
            end_dt = _parse_ts(timestamp_end)
        except ValueError:
            continue
        records.append(
            AlertRecord(
                evidence_id=str(candidate.get("evidence_id", "")),
                evidence_type=str(candidate.get("evidence_type", "unknown")),
                incident_id=str(candidate.get("incident_id", incident_id)),
                service=str(candidate.get("service", "unknown")),
                detected_at=anchor_ts,
                anchor_dt=anchor_dt,
                timestamp_start=timestamp_start,
                timestamp_end=timestamp_end,
                start_dt=start_dt,
                end_dt=end_dt,
                score=score,
                summary=str(candidate.get("summary", "")),
                signals=[str(signal) for signal in candidate.get("signals", [])],
                details=dict(candidate.get("details", {})),
                candidate=candidate,
            )
        )
    records.sort(key=lambda record: (record.anchor_dt, record.evidence_id))
    return records


def _session_groups(records: list[AlertRecord], gap_sec: int) -> list[list[AlertRecord]]:
    if not records:
        return []
    sessions: list[list[AlertRecord]] = [[records[0]]]
    for record in records[1:]:
        previous = sessions[-1][-1]
        gap = (record.anchor_dt - previous.anchor_dt).total_seconds()
        if gap <= gap_sec:
            sessions[-1].append(record)
        else:
            sessions.append([record])
    return sessions


def _build_service_graph(
    incident: dict[str, Any],
    records: list[AlertRecord],
) -> tuple[nx.Graph, list[dict[str, Any]]]:
    graph = nx.Graph()
    for node in incident.get("topology", {}).get("nodes", []):
        node_id = str(node.get("id", ""))
        if node_id:
            graph.add_node(node_id, **node)
    for record in records:
        graph.add_node(record.service)

    for edge in incident.get("topology", {}).get("edges", []):
        source = str(edge.get("from", ""))
        target = str(edge.get("to", ""))
        if source and target:
            graph.add_edge(
                source,
                target,
                sources=_edge_sources(graph, source, target, "topology"),
                protocol=edge.get("protocol"),
            )

    trace_edges_added: dict[tuple[str, str], dict[str, Any]] = {}
    for trace in incident.get("traces", []):
        source = str(trace.get("from", ""))
        target = str(trace.get("to", ""))
        if not source or not target:
            continue
        key = tuple(sorted((source, target)))
        entry = trace_edges_added.setdefault(
            key,
            {
                "from": source,
                "to": target,
                "count": 0,
                "error_count": 0,
                "max_p99_ms": 0.0,
            },
        )
        entry["count"] += int(trace.get("count", 0) or 0)
        entry["error_count"] += int(trace.get("error_count", 0) or 0)
        entry["max_p99_ms"] = max(
            float(entry["max_p99_ms"]),
            float(trace.get("p99_ms", 0.0) or 0.0),
        )
        graph.add_edge(
            source,
            target,
            sources=_edge_sources(graph, source, target, "trace"),
            protocol=trace.get("protocol", "trace"),
        )

    trace_edges = sorted(
        trace_edges_added.values(),
        key=lambda edge: (edge["from"], edge["to"]),
    )
    return graph, trace_edges


def _edge_sources(graph: nx.Graph, source: str, target: str, new_source: str) -> list[str]:
    existing = []
    if graph.has_edge(source, target):
        existing = list(graph.edges[source, target].get("sources", []))
    return sorted({*existing, new_source})


def _topology_groups(
    session: list[AlertRecord],
    graph: nx.Graph,
    trace_edges_added: list[dict[str, Any]],
    max_hop: int,
) -> list[tuple[list[AlertRecord], dict[str, Any]]]:
    by_service: dict[str, list[AlertRecord]] = defaultdict(list)
    for record in session:
        by_service[record.service].append(record)

    services = sorted(by_service)
    relation_graph = nx.Graph()
    relation_graph.add_nodes_from(services)
    service_distances: list[dict[str, Any]] = []

    for index, service_a in enumerate(services):
        for service_b in services[index + 1 :]:
            distance = _service_distance(graph, service_a, service_b)
            if distance is not None and distance <= max_hop:
                relation_graph.add_edge(service_a, service_b)
                service_distances.append(
                    {
                        "from": service_a,
                        "to": service_b,
                        "distance": distance,
                    }
                )

    groups: list[tuple[list[AlertRecord], dict[str, Any]]] = []
    for component in sorted(nx.connected_components(relation_graph), key=lambda c: sorted(c)):
        group_records: list[AlertRecord] = []
        for service in sorted(component):
            group_records.extend(by_service[service])
        group_records.sort(key=lambda record: (record.anchor_dt, record.evidence_id))
        topology_details = {
            "max_hop": max_hop,
            "service_distances": [
                item
                for item in service_distances
                if item["from"] in component and item["to"] in component
            ],
            "trace_edges_added": [
                edge
                for edge in trace_edges_added
                if edge["from"] in component or edge["to"] in component
            ],
        }
        groups.append((group_records, topology_details))
    return groups


def _service_distance(graph: nx.Graph, service_a: str, service_b: str) -> int | None:
    if service_a == service_b:
        return 0
    if service_a not in graph or service_b not in graph:
        return None
    try:
        return int(nx.shortest_path_length(graph, service_a, service_b))
    except nx.NetworkXNoPath:
        return None


def _summarize_cluster(
    cluster_id: str,
    records: list[AlertRecord],
    topology_details: dict[str, Any],
) -> dict[str, Any]:
    signals = Counter(signal for record in records for signal in record.signals)
    top_evidence = sorted(
        records,
        key=lambda record: (-record.score, record.anchor_dt, record.evidence_id),
    )[:5]
    return {
        "cluster_id": cluster_id,
        "alert_count": len(records),
        "services": sorted({record.service for record in records}),
        "time_range": [
            _format_ts(min(record.start_dt for record in records)),
            _format_ts(max(record.end_dt for record in records)),
        ],
        "max_score": round(max(record.score for record in records), 4),
        "mean_score": round(mean(record.score for record in records), 4),
        "dominant_signals": [
            signal
            for signal, _ in sorted(
                signals.items(),
                key=lambda item: (-item[1], item[0]),
            )[:8]
        ],
        "fingerprints": sorted({_fingerprint(record) for record in records}),
        "evidence_ids": [record.evidence_id for record in records],
        "top_evidence": [
            {
                "evidence_id": record.evidence_id,
                "evidence_type": record.evidence_type,
                "service": record.service,
                "detected_at": record.detected_at,
                "score": round(record.score, 4),
                "summary": record.summary,
                "signals": record.signals,
            }
            for record in top_evidence
        ],
        "topology_details": topology_details,
    }


def _fingerprint(record: AlertRecord) -> str:
    if record.evidence_type == "metric":
        metric = record.details.get("metric")
        if metric:
            return f"metric:{record.service}:{metric}"
    if record.evidence_type == "log":
        template_id = record.details.get("template_id")
        if template_id:
            return f"log:{record.service}:{template_id}"
    suffix = record.evidence_id.rsplit(":", 1)[-1] or _stable_id(record.evidence_id)
    return f"{record.evidence_type}:{record.service}:{suffix}"


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )


def _format_ts(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _short_incident_id(incident_id: str) -> str:
    match = re.match(r"^(E\d+)", incident_id)
    return match.group(1) if match else incident_id


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _stable_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--incident", required=True)
    parser.add_argument("--evidence", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--gap-sec", type=int, default=300)
    parser.add_argument("--max-hop", type=int, default=2)
    parser.add_argument("--min-score", type=float, default=0.28)
    args = parser.parse_args()

    incident_path = Path(args.incident)
    incident = load_incident(incident_path)
    detection = load_detection(Path(args.evidence)) if args.evidence else None
    correlation = correlate_incident(
        incident,
        detection=detection,
        source_file=incident_path.as_posix(),
        gap_sec=args.gap_sec,
        max_hop=args.max_hop,
        min_score=args.min_score,
    )
    payload = json.dumps(correlation, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
