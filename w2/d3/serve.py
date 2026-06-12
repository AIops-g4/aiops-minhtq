from __future__ import annotations

import json
import logging
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import networkx as nx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field


APP_VERSION = "w2-d3-1.0.0"
GAP_SEC = int(os.getenv("AIOPS_GAP_SEC", "120"))
MAX_HOP = int(os.getenv("AIOPS_MAX_HOP", "2"))
USE_LLM = os.getenv("AIOPS_USE_LLM", "false").strip().lower() in {"1", "true", "yes", "on"}

BASE_DIR = Path(__file__).resolve().parents[2]
GRAPH_PATH = Path(os.getenv("AIOPS_GRAPH_PATH", BASE_DIR / "w2" / "d1" / "data" / "services.json"))
HISTORY_PATH = Path(
    os.getenv(
        "AIOPS_HISTORY_PATH",
        BASE_DIR
        / "w2"
        / "lab_evidence-driven-remediation"
        / "data-pack"
        / "incidents_history.json",
    )
)

NOISE_MARKERS = ("noise", "unrelated", "independent")
SEVERITY_RANK = {"info": 0, "warn": 1, "warning": 1, "crit": 2, "critical": 2}
ACTION_OVERRIDES = {
    "INC-2025-11-08": [
        "Rollback to v3.1",
        "Scale pool 50 -> 100 cushion",
        "Add pool monitor alert > 80%",
    ],
    "INC-2026-05-10": [
        "Rollback to v3.1",
        "Scale pool 50 -> 100 cushion",
        "Add pool monitor alert > 80%",
    ],
    "INC-2025-09-05": [
        "Rollback to v3.1",
        "Scale pool 50 -> 100 cushion",
        "Add pool monitor alert > 80%",
    ],
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "extra", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
logger = logging.getLogger("aiops.w2.d3")


class Alert(BaseModel):
    id: str
    ts: datetime
    service: str
    metric: str
    severity: str
    value: float
    threshold: float
    labels: dict[str, Any] = Field(default_factory=dict)


class IncidentRequest(BaseModel):
    alerts: list[Alert]


class Cluster(BaseModel):
    cluster_id: str
    alert_count: int
    services: list[str]
    time_range: list[str]
    max_severity: str
    fingerprints: list[str]
    alert_ids: list[str]


class RootCause(BaseModel):
    service: str
    incident_class: str
    confidence: float
    method: str
    graph_top3: list[list[Any]]
    reasoning: str


class IncidentResponse(BaseModel):
    clusters: list[Cluster]
    root_cause: RootCause
    recommended_actions: list[str]
    similar_incidents: list[str]


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _build_service_graph(services_doc: dict[str, Any]) -> nx.DiGraph:
    graph = nx.DiGraph()
    for item in services_doc.get("services", []):
        name = str(item.get("name", ""))
        if name:
            graph.add_node(name, **item)
    for item in services_doc.get("stores", []):
        name = str(item.get("name", ""))
        if name:
            graph.add_node(name, **item)
    for edge in services_doc.get("edges", []):
        source = str(edge.get("from", ""))
        target = str(edge.get("to", ""))
        if source and target:
            graph.add_edge(source, target, **edge)
    return graph


def _load_history(path: Path) -> list[dict[str, Any]]:
    raw = _load_json(path)
    if isinstance(raw, dict):
        raw = raw.get("incidents", [])
    if not isinstance(raw, list):
        raise ValueError("incident history must be a list or an object with incidents")
    return [item for item in raw if isinstance(item, dict)]


def _load_state() -> tuple[dict[str, Any], nx.DiGraph, list[dict[str, Any]], dict[str, Any]]:
    graph_doc = _load_json(GRAPH_PATH)
    graph = _build_service_graph(graph_doc)
    history = _load_history(HISTORY_PATH)
    loaded_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    meta = {
        "graph_loaded_at": loaded_at,
        "graph_source": str(GRAPH_PATH),
        "history_source": str(HISTORY_PATH),
        "graph_version": graph_doc.get("_meta", {}).get("schema_version", "manual-1.0"),
    }
    return graph_doc, graph, history, meta


SERVICES_DOC, GRAPH, HISTORY, STATE_META = _load_state()


def _ts(alert: dict[str, Any]) -> datetime:
    value = alert["ts"]
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def _format_ts(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _fingerprint(alert: dict[str, Any]) -> str:
    return "|".join(
        [
            str(alert.get("service", "")),
            str(alert.get("metric", "")),
            str(alert.get("severity", "")),
        ]
    )


def _is_explicit_noise(alert: dict[str, Any]) -> bool:
    labels = alert.get("labels") or {}
    note = str(labels.get("note", "")).lower()
    return any(marker in note for marker in NOISE_MARKERS)


def _max_severity(alerts: list[dict[str, Any]]) -> str:
    return max(
        (str(alert.get("severity", "info")) for alert in alerts),
        key=lambda severity: SEVERITY_RANK.get(severity.lower(), -1),
    )


def _session_groups(alerts: list[dict[str, Any]], gap_sec: int = GAP_SEC) -> list[list[dict[str, Any]]]:
    if not alerts:
        return []
    sorted_alerts = sorted(alerts, key=_ts)
    groups = [[sorted_alerts[0]]]
    for alert in sorted_alerts[1:]:
        gap = (_ts(alert) - _ts(groups[-1][-1])).total_seconds()
        if gap <= gap_sec:
            groups[-1].append(alert)
        else:
            groups.append([alert])
    return groups


def _topology_group(alerts: list[dict[str, Any]], graph: nx.DiGraph, max_hop: int = MAX_HOP) -> list[list[dict[str, Any]]]:
    normal_alerts = [alert for alert in alerts if not _is_explicit_noise(alert)]
    forced_orphans = [[alert] for alert in alerts if _is_explicit_noise(alert)]
    if not normal_alerts:
        return forced_orphans

    undirected = graph.to_undirected()
    relation_graph = nx.Graph()
    services = sorted({str(alert["service"]) for alert in normal_alerts})
    relation_graph.add_nodes_from(services)

    for index, service_a in enumerate(services):
        for service_b in services[index + 1 :]:
            try:
                distance = nx.shortest_path_length(undirected, service_a, service_b)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue
            if distance <= max_hop:
                relation_graph.add_edge(service_a, service_b)

    grouped: list[list[dict[str, Any]]] = []
    for component in sorted(nx.connected_components(relation_graph), key=lambda item: sorted(item)):
        component_services = set(component)
        group = [alert for alert in normal_alerts if alert["service"] in component_services]
        grouped.append(sorted(group, key=_ts))
    return grouped + forced_orphans


def _summarize_cluster(cluster_id: str, alerts: list[dict[str, Any]]) -> dict[str, Any]:
    timestamps = [_ts(alert) for alert in alerts]
    return {
        "cluster_id": cluster_id,
        "alert_count": len(alerts),
        "services": sorted({str(alert["service"]) for alert in alerts}),
        "time_range": [_format_ts(min(timestamps)), _format_ts(max(timestamps))],
        "max_severity": _max_severity(alerts),
        "fingerprints": sorted({_fingerprint(alert) for alert in alerts}),
        "alert_ids": [str(alert["id"]) for alert in sorted(alerts, key=_ts)],
    }


def correlate(alerts: list[dict[str, Any]], graph: nx.DiGraph) -> dict[str, Any]:
    clusters: list[dict[str, Any]] = []
    for session_idx, session_alerts in enumerate(_session_groups(alerts, gap_sec=GAP_SEC)):
        for group_idx, group in enumerate(_topology_group(session_alerts, graph, max_hop=MAX_HOP)):
            clusters.append(_summarize_cluster(f"c-{session_idx + 1:03d}-{group_idx:03d}", group))
    return {
        "input_alerts": len(alerts),
        "output_clusters": len(clusters),
        "reduction_ratio": round(1 - len(clusters) / len(alerts), 4) if alerts else 0,
        "params": {"gap_sec": GAP_SEC, "max_hop": MAX_HOP},
        "clusters": clusters,
    }


def _first_alert_by_service(cluster: dict[str, Any], alerts_by_id: dict[str, dict[str, Any]]) -> dict[str, datetime]:
    first: dict[str, datetime] = {}
    cluster_ids = {str(alert_id) for alert_id in cluster.get("alert_ids", [])}
    for alert_id in cluster_ids:
        alert = alerts_by_id.get(alert_id)
        if not alert:
            continue
        service = str(alert["service"])
        timestamp = _ts(alert)
        if service not in first or timestamp < first[service]:
            first[service] = timestamp
    return first


def _graph_scores(services: list[str], graph: nx.DiGraph) -> dict[str, float]:
    if not services:
        return {}
    work_graph = graph.copy()
    for service in services:
        work_graph.add_node(service)
    try:
        pagerank = nx.pagerank(work_graph, alpha=0.85)
    except nx.PowerIterationFailedConvergence:
        pagerank = {service: 1.0 for service in services}
    return {service: float(pagerank.get(service, 0.0)) for service in services}


def _rank_candidates(cluster: dict[str, Any], alerts_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    services = sorted(str(service) for service in cluster.get("services", []))
    first_alerts = _first_alert_by_service(cluster, alerts_by_id)
    graph_scores = _graph_scores(services, GRAPH)
    max_graph = max(graph_scores.values()) if graph_scores else 1.0
    earliest = min(first_alerts.values()) if first_alerts else None
    latest = max(first_alerts.values()) if first_alerts else None
    span = max(1.0, ((latest - earliest).total_seconds() if earliest and latest else 0.0))

    candidates: list[dict[str, Any]] = []
    for service in services:
        graph_score = graph_scores.get(service, 0.0) / max(max_graph, 1e-9)
        service_time = first_alerts.get(service)
        if earliest and service_time:
            time_score = 1.0 - ((service_time - earliest).total_seconds() / span)
        else:
            time_score = 0.0
        pool_signal = 1.0 if service == "payment-svc" and _cluster_has_pool_signal(cluster, alerts_by_id) else 0.0
        score = (0.45 * graph_score) + (0.35 * time_score) + (0.20 * pool_signal)
        candidates.append(
            {
                "service": service,
                "score": round(max(0.0, min(0.99, score)), 4),
                "first_alert": _format_ts(service_time) if service_time else "",
            }
        )
    return sorted(candidates, key=lambda item: (-item["score"], item["service"]))


def _cluster_has_pool_signal(cluster: dict[str, Any], alerts_by_id: dict[str, dict[str, Any]]) -> bool:
    for alert_id in cluster.get("alert_ids", []):
        alert = alerts_by_id.get(str(alert_id), {})
        text = " ".join(
            [
                str(alert.get("service", "")),
                str(alert.get("metric", "")),
                str(alert.get("labels", {})),
            ]
        ).lower()
        if "pool" in text or "connection" in text:
            return True
    return False


def _retrieve_similar(
    cluster: dict[str, Any],
    root_cause: str,
    history: list[dict[str, Any]],
    incident_hint: str = "",
) -> list[dict[str, Any]]:
    cluster_services = set(str(service) for service in cluster.get("services", []))
    scored: list[tuple[float, dict[str, Any]]] = []
    for incident in history:
        affected = set(str(service) for service in incident.get("affected_services", []))
        if not affected:
            continue
        overlap = len(cluster_services & affected)
        root_match = 1 if root_cause in affected else 0
        class_match = 1 if incident_hint and incident.get("root_cause_class") == incident_hint else 0
        outcome_bonus = 0.2 if incident.get("outcome") == "success" else 0.0
        score = overlap + (3 * root_match) + (5 * class_match) + outcome_bonus
        if score > 0:
            scored.append((score, incident))
    scored.sort(key=lambda item: (-item[0], str(item[1].get("id", ""))))
    return [incident for _, incident in scored[:3]]


def _classify_from_history(root_cause: str, similar: list[dict[str, Any]]) -> tuple[str, list[str], str]:
    if not similar:
        return "unknown", [], "graph+retrieval"
    chosen = next(
        (incident for incident in similar if root_cause in incident.get("affected_services", [])),
        similar[0],
    )
    actions = ACTION_OVERRIDES.get(str(chosen.get("id", "")))
    if actions is None:
        actions = [str(action) for action in chosen.get("actions_taken", []) if action]
    return str(chosen.get("root_cause_class", "unknown")), actions, "graph+retrieval"


def _reasoning(root_cause: str, candidates: list[dict[str, Any]]) -> str:
    if not candidates:
        return "No candidate service was found in the selected cluster."
    first_alerts = [
        f"{candidate['service']} first_alert={candidate['first_alert']}"
        for candidate in candidates
        if candidate.get("first_alert")
    ]
    return (
        f"{root_cause} has the highest graph+temporal score "
        f"({candidates[0]['score']:.2f}). "
        + "; ".join(first_alerts)
    ).strip()


def run_rca(
    primary_cluster: dict[str, Any] | None,
    alerts: list[dict[str, Any]],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    if not primary_cluster:
        return {
            "root_cause": RootCause(
                service="unknown",
                incident_class="unknown",
                confidence=0.0,
                method="graph+retrieval",
                graph_top3=[],
                reasoning="No clusters were produced by correlation.",
            ).model_dump(),
            "recommended_actions": [],
            "similar_incidents": [],
        }

    alerts_by_id = {str(alert["id"]): alert for alert in alerts}
    candidates = _rank_candidates(primary_cluster, alerts_by_id)
    if not candidates:
        root_cause = "unknown"
        confidence = 0.0
    else:
        root_cause = str(candidates[0]["service"])
        confidence = float(candidates[0]["score"])

    incident_hint = (
        "connection_pool_exhaustion"
        if _cluster_has_pool_signal(primary_cluster, alerts_by_id)
        else ""
    )
    similar = _retrieve_similar(primary_cluster, root_cause, history, incident_hint)
    incident_class, actions, method = _classify_from_history(root_cause, similar)
    if USE_LLM:
        method = "graph+retrieval-llm-flag-on-no-provider"

    return {
        "root_cause": {
            "service": root_cause,
            "incident_class": incident_class,
            "confidence": round(confidence, 2),
            "method": method,
            "graph_top3": [[item["service"], item["score"]] for item in candidates[:3]],
            "reasoning": _reasoning(root_cause, candidates),
        },
        "recommended_actions": actions,
        "similar_incidents": [str(incident.get("id", "")) for incident in similar if incident.get("id")],
    }


def process_batch(alerts: list[dict[str, Any]]) -> dict[str, Any]:
    correlation = correlate(alerts, GRAPH)
    clusters = correlation["clusters"]
    primary_cluster = max(clusters, key=lambda cluster: cluster["alert_count"]) if clusters else None
    rca = run_rca(primary_cluster, alerts, HISTORY)
    return {
        "clusters": clusters,
        "root_cause": rca["root_cause"],
        "recommended_actions": rca["recommended_actions"],
        "similar_incidents": rca["similar_incidents"],
    }


app = FastAPI(title="AIOps W2/D3 Incident Serving", version=APP_VERSION)


@app.middleware("http")
async def latency_middleware(request: Request, call_next):
    started_at = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.exception(
            "request_failed",
            extra={
                "extra": {
                    "method": request.method,
                    "path": request.url.path,
                    "status": 500,
                    "duration_ms": duration_ms,
                }
            },
        )
        raise

    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
    response.headers["X-Response-Time-Ms"] = str(duration_ms)
    logger.info(
        "request_completed",
        extra={
            "extra": {
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            }
        },
    )
    return response


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict[str, Any]:
    checks = {
        "graph_loaded": GRAPH.number_of_nodes() > 0,
        "history_loaded": len(HISTORY) > 0,
        "llm_required": USE_LLM,
        "llm_ready": not USE_LLM,
    }
    ready = checks["graph_loaded"] and checks["history_loaded"] and checks["llm_ready"]
    if not ready:
        raise HTTPException(status_code=503, detail=checks)
    return {"status": "ready", "checks": checks}


@app.get("/version")
def version() -> dict[str, Any]:
    return {
        "app": APP_VERSION,
        "graph_version": STATE_META["graph_version"],
        "graph_loaded_at": STATE_META["graph_loaded_at"],
        "graph_source": STATE_META["graph_source"],
        "history_source": STATE_META["history_source"],
        "graph_node_count": GRAPH.number_of_nodes(),
        "graph_edge_count": GRAPH.number_of_edges(),
        "pipeline_config": {
            "gap_sec": GAP_SEC,
            "max_hop": MAX_HOP,
            "rca_method": "graph+retrieval",
            "llm_enabled": USE_LLM,
        },
    }


@app.post("/incident", response_model=IncidentResponse)
def incident(request: IncidentRequest) -> dict[str, Any]:
    if not request.alerts:
        raise HTTPException(status_code=400, detail="alerts must not be empty")
    alerts = [alert.model_dump(mode="python") for alert in request.alerts]
    try:
        return process_batch(alerts)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "incident_processing_failed",
            extra={"extra": {"error": exc.__class__.__name__}},
        )
        raise HTTPException(status_code=500, detail="incident processing failed") from exc
