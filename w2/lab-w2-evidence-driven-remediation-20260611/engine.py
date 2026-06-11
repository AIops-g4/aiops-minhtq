"""End-to-end remediation decision engine with optional Groq LLM augmentation."""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from correlation import correlate_incident
from features import detect_incident, load_incident
from rca import rank_root_causes


SCHEMA_VERSION = "1.0"
DEFAULT_ARTIFACTS_DIR = Path("artifacts")
DEFAULT_MODEL = "openai/gpt-oss-20b"
OUTCOME_WEIGHT = {"success": 1.0, "partial": 0.55, "failed": 0.1}
FALLBACK_TEAM = "platform-team"


@dataclass(frozen=True)
class ParsedAction:
    name: str
    params: dict[str, str]


def decide(
    incident_path: Path,
    history_path: Path,
    actions_path: Path,
    artifacts_dir: Path = DEFAULT_ARTIFACTS_DIR,
    model: str = DEFAULT_MODEL,
    llm_mode: str = "auto",
) -> dict[str, Any]:
    """Run all local ranking stages, optionally ask an LLM, and write artifacts."""
    incident = load_incident(incident_path)
    history = _load_json(history_path)
    actions_catalog = _load_actions(actions_path)

    detection = detect_incident(incident, source_file=incident_path.as_posix())
    correlation = correlate_incident(
        incident,
        detection=detection,
        source_file=incident_path.as_posix(),
    )
    rca = rank_root_causes(
        incident,
        detection=detection,
        correlation=correlation,
        source_file=incident_path.as_posix(),
    )

    incident_id = _short_incident_id(str(detection.get("incident_id", "")))
    remediation_dir = artifacts_dir / "remediation"
    remediation_dir.mkdir(parents=True, exist_ok=True)

    context = _build_decision_context(
        incident=incident,
        detection=detection,
        correlation=correlation,
        rca=rca,
        history=history,
        actions_catalog=actions_catalog,
        incident_id=incident_id,
    )
    prompt_payload = _build_llm_prompt(context, actions_catalog)
    _write_json(remediation_dir / f"{incident_id}_llm_prompt.json", prompt_payload)

    llm_result = _call_llm(prompt_payload, model=model, llm_mode=llm_mode)
    _write_json(remediation_dir / f"{incident_id}_llm_response.json", llm_result)

    fallback = _fallback_decision(context, actions_catalog)
    llm_decision = _validated_llm_decision(llm_result, context, actions_catalog)
    if llm_decision is None:
        decision = fallback
        decision["method"] = llm_result["method"]
    elif not _llm_agrees_with_guardrails(llm_decision, fallback):
        decision = fallback
        decision["method"] = "llm-guarded-fallback"
        decision["llm_evidence"] = llm_decision.get("llm_evidence", [])
        decision["reasoning"] = (
            fallback.get("reasoning", "")
            + "; guarded LLM suggestion="
            + llm_decision.get("selected_action", "")
        )
    else:
        decision = llm_decision
        decision["method"] = "llm-augmented"

    audit_record = _build_audit_record(
        incident_id=incident_id,
        decision=decision,
        context=context,
        actions_catalog=actions_catalog,
    )
    _write_json(remediation_dir / f"{incident_id}_decision.json", audit_record)
    _append_jsonl(remediation_dir / "audit.jsonl", audit_record)
    return audit_record


def _build_decision_context(
    incident: dict[str, Any],
    detection: dict[str, Any],
    correlation: dict[str, Any],
    rca: dict[str, Any],
    history: list[dict[str, Any]],
    actions_catalog: list[dict[str, Any]],
    incident_id: str,
) -> dict[str, Any]:
    cluster_ranking = _primary_cluster_ranking(rca)
    top_candidate = (cluster_ranking.get("candidates") or [{}])[0]
    cluster = _cluster_by_id(correlation, str(cluster_ranking.get("cluster_id", "")))
    live_features = _live_feature_summary(incident, detection, cluster, cluster_ranking)
    neighbors = _retrieve_neighbors(live_features, history, top_k=3)
    action_votes = _vote_actions(neighbors, actions_catalog, live_features)
    return {
        "incident_id": incident_id,
        "severity": incident.get("trigger_alert", {}).get("severity", "unknown"),
        "alert_service": incident.get("trigger_alert", {}).get("service", "unknown"),
        "cluster": cluster,
        "rca": rca,
        "primary_ranking": cluster_ranking,
        "top_candidate": top_candidate,
        "live_features": live_features,
        "top_3_neighbors": neighbors,
        "action_votes": action_votes,
    }


def _build_llm_prompt(
    context: dict[str, Any],
    actions_catalog: list[dict[str, Any]],
) -> dict[str, Any]:
    candidate_services = [
        item.get("service")
        for item in context["primary_ranking"].get("candidates", [])
        if item.get("service")
    ]
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "root_cause_service": {"type": "string", "enum": candidate_services or ["unknown"]},
            "root_cause_class": {"type": "string"},
            "selected_action": {
                "type": "string",
                "enum": [str(action["name"]) for action in actions_catalog],
            },
            "params": {"type": "object"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "evidence": {"type": "array", "items": {"type": "string"}},
            "reasoning": {"type": "string"},
        },
        "required": [
            "root_cause_service",
            "root_cause_class",
            "selected_action",
            "params",
            "confidence",
            "evidence",
            "reasoning",
        ],
    }
    compact_context = {
        "incident_id": context["incident_id"],
        "severity": context["severity"],
        "alert_service": context["alert_service"],
        "candidate_services": candidate_services,
        "top_candidates": context["primary_ranking"].get("candidates", [])[:4],
        "cluster_top_evidence": context["cluster"].get("top_evidence", [])[:8],
        "dominant_signals": context["live_features"]["signals"],
        "top_neighbors": context["top_3_neighbors"],
        "action_votes": context["action_votes"],
        "actions_catalog": actions_catalog,
    }
    return {
        "system": (
            "You are a senior SRE assistant. Return only JSON matching the schema. "
            "Use only candidate services and actions in the provided context. "
            "If evidence is novel or unsafe, select page_oncall."
        ),
        "user": compact_context,
        "response_schema": schema,
    }


def _call_llm(prompt_payload: dict[str, Any], model: str, llm_mode: str) -> dict[str, Any]:
    if llm_mode == "off":
        return {"ok": False, "method": "llm-off-fallback", "error": "LLM disabled"}

    _load_dotenv(Path(".env"))
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        method = "llm-missing-key-fallback"
        if llm_mode == "required":
            method = "llm-error-fallback"
        return {"ok": False, "method": method, "error": "GROQ_API_KEY is not set"}

    try:
        from groq import Groq
    except ImportError as exc:
        return {"ok": False, "method": "llm-error-fallback", "error": str(exc)}

    try:
        client = Groq(api_key=api_key)
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt_payload["system"]},
                {"role": "user", "content": json.dumps(prompt_payload["user"])},
            ],
            temperature=0,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "remediation_decision",
                    "schema": prompt_payload["response_schema"],
                },
            },
        )
        content = completion.choices[0].message.content or "{}"
        return {
            "ok": True,
            "method": "llm-raw",
            "model": model,
            "content": json.loads(content),
        }
    except Exception as exc:  # Groq/API/JSON errors should never break audit output.
        return {"ok": False, "method": "llm-error-fallback", "error": str(exc)}


def _validated_llm_decision(
    llm_result: dict[str, Any],
    context: dict[str, Any],
    actions_catalog: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not llm_result.get("ok"):
        return None

    content = llm_result.get("content")
    if not isinstance(content, dict):
        return None

    candidate_services = {
        str(item.get("service"))
        for item in context["primary_ranking"].get("candidates", [])
        if item.get("service")
    }
    root_service = str(content.get("root_cause_service", ""))
    if root_service not in candidate_services:
        return None

    action_name = str(content.get("selected_action", ""))
    if action_name not in _action_names(actions_catalog):
        return None

    params = _normalize_action_params(action_name, dict(content.get("params", {})), root_service)
    if not _has_required_params(action_name, params, actions_catalog):
        return None

    try:
        confidence = _clamp01(float(content.get("confidence", 0.0)))
    except (TypeError, ValueError):
        return None

    return {
        "root_cause_service": root_service,
        "root_cause_class": str(content.get("root_cause_class", "other")),
        "selected_action": action_name,
        "params": params,
        "confidence": confidence,
        "reasoning": str(content.get("reasoning", "")),
        "llm_evidence": [str(item) for item in content.get("evidence", [])],
    }


def _fallback_decision(
    context: dict[str, Any],
    actions_catalog: list[dict[str, Any]],
) -> dict[str, Any]:
    live = context["live_features"]
    top_service = str(context["top_candidate"].get("service") or live["services"][0])
    text = " ".join(live["keywords"] + live["signals"]).lower()
    votes = context["action_votes"]
    best_vote = votes[0] if votes else {"action": "page_oncall", "params": {"team": FALLBACK_TEAM}, "score": 0.0}
    neighbor_score = max([n["similarity"] for n in context["top_3_neighbors"]] or [0.0])
    rca_conf = _rca_confidence(context)

    if any(token in text for token in ("tls", "x509", "certificate")):
        return _decision("page_oncall", {"team": FALLBACK_TEAM}, 0.72, top_service, "tls_or_cert_requires_human")
    if any(token in text for token in ("dns", "nxdomain")):
        return _decision("dns_config_rollback", {"configmap_name": "dns-config", "target_revision": "previous"}, 0.68, top_service, "dns_config_signal")
    if any(token in text for token in ("oom", "outofmemory", "evicted", "memory")):
        return _decision("restart_pod", {"service": top_service, "pod_selector": "app=" + top_service}, 0.66, top_service, "memory_or_eviction_signal")
    if any(token in text for token in ("pool", "connectionpool", "exhausted")):
        if top_service not in _services_with_pool_evidence(context):
            return _decision("page_oncall", {"team": FALLBACK_TEAM}, 0.6, top_service, "conflicting_pool_evidence")
        preferred = _first_vote_by_order(votes, ["rollback_service", "increase_pool_size"])
        if preferred:
            return _vote_decision(preferred, top_service, "pool_signal_history_vote")
        return _decision("increase_pool_size", {"service": top_service, "from_value": "50", "to_value": "100"}, 0.7, top_service, "pool_signal_default")

    if neighbor_score < 0.28 or rca_conf < 0.35:
        return _decision("page_oncall", {"team": FALLBACK_TEAM}, 0.58, top_service, "novel_or_low_confidence")

    if best_vote["action"] == "page_oncall" and neighbor_score >= 0.45:
        return _vote_decision(best_vote, top_service, "history_vote_page")
    if best_vote["action"] != "page_oncall":
        return _vote_decision(best_vote, top_service, "history_vote")
    return _decision("page_oncall", {"team": FALLBACK_TEAM}, 0.55, top_service, "no_safe_auto_action")


def _llm_agrees_with_guardrails(
    llm_decision: dict[str, Any],
    fallback: dict[str, Any],
) -> bool:
    if llm_decision["selected_action"] == fallback["selected_action"]:
        return True
    if fallback["selected_action"] == "page_oncall":
        return False
    if fallback["selected_action"] == "rollback_service" and llm_decision["selected_action"] == "increase_pool_size":
        return False
    if fallback["selected_action"] == "restart_pod" and llm_decision["selected_action"] == "rollback_service":
        return True
    return False


def _build_audit_record(
    incident_id: str,
    decision: dict[str, Any],
    context: dict[str, Any],
    actions_catalog: list[dict[str, Any]],
) -> dict[str, Any]:
    action_meta = next(
        (action for action in actions_catalog if action.get("name") == decision["selected_action"]),
        {},
    )
    evidence = {
        "method": decision.get("method"),
        "reasoning": decision.get("reasoning", ""),
        "root_cause_service": decision.get("root_cause_service"),
        "root_cause_class": decision.get("root_cause_class", "other"),
        "rca_top_candidates": context["primary_ranking"].get("candidates", [])[:3],
        "top_3_neighbors": context["top_3_neighbors"],
        "consensus_score": _consensus_score(context["action_votes"]),
        "action_votes": context["action_votes"],
        "dominant_signals": context["live_features"]["signals"],
        "blast_radius_check": {
            "blast_radius_services": action_meta.get("blast_radius_services", 0),
            "allowed": True,
        },
        "llm_evidence": decision.get("llm_evidence", []),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "incident_id": incident_id,
        "selected_action": decision["selected_action"],
        "params": decision["params"],
        "confidence": round(_clamp01(float(decision["confidence"])), 4),
        "selected_action_meta": action_meta,
        "evidence": evidence,
        "top_3_neighbors": context["top_3_neighbors"],
        "consensus_score": evidence["consensus_score"],
        "blast_radius_check": evidence["blast_radius_check"],
    }


def _primary_cluster_ranking(rca: dict[str, Any]) -> dict[str, Any]:
    rankings = rca.get("root_cause_rankings", [])
    if not rankings:
        return {"cluster_id": "", "candidates": [], "confidence": {"level": "low"}}
    return max(rankings, key=lambda item: len(item.get("candidates", [])))


def _cluster_by_id(correlation: dict[str, Any], cluster_id: str) -> dict[str, Any]:
    for cluster in correlation.get("clusters", []):
        if cluster.get("cluster_id") == cluster_id:
            return cluster
    return (correlation.get("clusters") or [{}])[0]


def _live_feature_summary(
    incident: dict[str, Any],
    detection: dict[str, Any],
    cluster: dict[str, Any],
    ranking: dict[str, Any],
) -> dict[str, Any]:
    services = [
        str(item.get("service"))
        for item in ranking.get("candidates", [])
        if item.get("service")
    ]
    if not services:
        services = [str(service) for service in cluster.get("services", []) if service]
    summaries = [
        str(item.get("summary", ""))
        for item in cluster.get("top_evidence", [])
        if item.get("summary")
    ]
    signals = sorted(
        {
            str(signal)
            for item in detection.get("evidence_candidates", [])
            for signal in item.get("signals", [])
        }
        | {str(signal) for signal in cluster.get("dominant_signals", [])}
    )
    keywords = _tokens(" ".join(summaries + signals + _raw_error_logs(incident)))
    trace_edges = {
        f"{trace.get('from')}->{trace.get('to')}"
        for trace in incident.get("traces", [])
        if float(trace.get("error_count", 0) or 0) > 0
    }
    metric_services = {
        str(item.get("service"))
        for item in detection.get("evidence_candidates", [])
        if item.get("evidence_type") == "metric"
    }
    return {
        "services": services,
        "signals": signals,
        "keywords": sorted(keywords),
        "summaries": summaries[:8],
        "trace_edges": sorted(trace_edges),
        "metric_services": sorted(metric_services),
    }


def _retrieve_neighbors(
    live_features: dict[str, Any],
    history: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    scored = []
    live_services = set(live_features["services"])
    live_keywords = set(live_features["keywords"])
    live_edges = set(live_features["trace_edges"])
    for incident in history:
        hist_services = set(incident.get("affected_services", []))
        hist_keywords = _tokens(" ".join(incident.get("log_signatures", [])))
        hist_edges = {
            f"{edge.get('from')}->{edge.get('to')}"
            for edge in incident.get("trace_signatures", [])
        }
        service_score = _jaccard(live_services, hist_services)
        keyword_score = _jaccard(live_keywords, hist_keywords)
        edge_score = _jaccard(live_edges, hist_edges)
        root_bonus = 0.2 if live_services and (next(iter(live_services)) in hist_services) else 0.0
        similarity = min(1.0, 0.45 * service_score + 0.35 * keyword_score + 0.20 * edge_score + root_bonus)
        scored.append(
            {
                "id": incident.get("id"),
                "similarity": round(similarity, 4),
                "root_cause_class": incident.get("root_cause_class", "other"),
                "affected_services": incident.get("affected_services", []),
                "actions_taken": incident.get("actions_taken", []),
                "outcome": incident.get("outcome", "unknown"),
                "mttr_minutes": incident.get("mttr_minutes"),
            }
        )
    scored.sort(key=lambda item: (-item["similarity"], item["id"] or ""))
    return scored[:top_k]


def _vote_actions(
    neighbors: list[dict[str, Any]],
    actions_catalog: list[dict[str, Any]],
    live_features: dict[str, Any],
) -> list[dict[str, Any]]:
    votes: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
    top_service = live_features["services"][0] if live_features["services"] else "unknown"
    for neighbor in neighbors:
        outcome_weight = OUTCOME_WEIGHT.get(str(neighbor.get("outcome")), 0.25)
        base = float(neighbor.get("similarity", 0.0)) * outcome_weight
        for raw_action in neighbor.get("actions_taken", []):
            parsed = _parse_history_action(str(raw_action), actions_catalog)
            if not parsed:
                continue
            params = _normalize_action_params(parsed.name, parsed.params, top_service)
            if "service" in params:
                params["service"] = top_service
            if parsed.name == "restart_pod":
                params["pod_selector"] = "app=" + top_service
            key = (parsed.name, tuple(sorted(params.items())))
            votes[key] += base
    outputs = [
        {
            "action": name,
            "params": dict(params),
            "score": round(score, 4),
        }
        for (name, params), score in votes.items()
    ]
    outputs.sort(key=lambda item: (-item["score"], item["action"]))
    return outputs


def _parse_history_action(
    raw_action: str,
    actions_catalog: list[dict[str, Any]],
) -> ParsedAction | None:
    parts = raw_action.split(":")
    if not parts:
        return None
    name = parts[0]
    catalog = next((item for item in actions_catalog if item.get("name") == name), None)
    if not catalog:
        return None
    param_names = list(catalog.get("params", []))
    values = parts[1:]
    if len(values) == 1 and "->" in values[0]:
        values = values[0].split("->", 1)
    params = {param: values[idx] for idx, param in enumerate(param_names) if idx < len(values)}
    return ParsedAction(name=name, params=params)


def _normalize_action_params(action_name: str, params: dict[str, Any], root_service: str) -> dict[str, Any]:
    normalized = {str(key): str(value) for key, value in params.items() if value is not None}
    if action_name in {"rollback_service", "increase_pool_size", "restart_pod"}:
        normalized.setdefault("service", root_service)
    if action_name == "rollback_service":
        normalized.setdefault("target_version", "previous")
    if action_name == "increase_pool_size":
        normalized.setdefault("from_value", "50")
        normalized.setdefault("to_value", "100")
    if action_name == "restart_pod":
        normalized.setdefault("pod_selector", "app=" + normalized.get("service", root_service))
    if action_name == "page_oncall":
        normalized.setdefault("team", FALLBACK_TEAM)
    if action_name == "dns_config_rollback":
        normalized.setdefault("configmap_name", "dns-config")
        normalized.setdefault("target_revision", "previous")
    return normalized


def _decision(
    action: str,
    params: dict[str, Any],
    confidence: float,
    root_service: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "root_cause_service": root_service,
        "root_cause_class": "other",
        "selected_action": action,
        "params": params,
        "confidence": confidence,
        "reasoning": reason,
    }


def _vote_decision(vote: dict[str, Any], root_service: str, reason: str) -> dict[str, Any]:
    return _decision(
        str(vote["action"]),
        dict(vote["params"]),
        min(0.9, 0.5 + float(vote.get("score", 0.0))),
        root_service,
        reason,
    )


def _first_vote(votes: list[dict[str, Any]], names: set[str]) -> dict[str, Any] | None:
    return next((vote for vote in votes if vote.get("action") in names), None)


def _first_vote_by_order(votes: list[dict[str, Any]], names: list[str]) -> dict[str, Any] | None:
    for name in names:
        match = _first_vote(votes, {name})
        if match:
            return match
    return None


def _services_with_pool_evidence(context: dict[str, Any]) -> set[str]:
    services: set[str] = set()
    for item in context["cluster"].get("top_evidence", []):
        summary = str(item.get("summary", "")).lower()
        signals = " ".join(str(signal).lower() for signal in item.get("signals", []))
        if any(token in summary + " " + signals for token in ("pool", "connectionpool", "exhausted")):
            service = item.get("service")
            if service:
                services.add(str(service))
    return services


def _has_required_params(
    action_name: str,
    params: dict[str, Any],
    actions_catalog: list[dict[str, Any]],
) -> bool:
    catalog = next((item for item in actions_catalog if item.get("name") == action_name), {})
    return all(param in params for param in catalog.get("params", []))


def _action_names(actions_catalog: list[dict[str, Any]]) -> set[str]:
    return {str(action.get("name")) for action in actions_catalog}


def _consensus_score(votes: list[dict[str, Any]]) -> float:
    if not votes:
        return 0.0
    total = sum(float(vote.get("score", 0.0)) for vote in votes)
    return round(float(votes[0].get("score", 0.0)) / total, 4) if total > 0 else 0.0


def _rca_confidence(context: dict[str, Any]) -> float:
    candidates = context["primary_ranking"].get("candidates", [])
    if not candidates:
        return 0.0
    return _clamp01(float(candidates[0].get("normalized_score", 0.0)))


def _raw_error_logs(incident: dict[str, Any]) -> list[str]:
    return [
        str(log.get("msg", ""))
        for log in incident.get("logs", [])
        if str(log.get("level", "")).upper() in {"ERROR", "WARN"}
    ][:100]


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9_]+", text.lower())
        if len(token) > 2 and not token.isdigit()
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _short_incident_id(incident_id: str) -> str:
    match = re.match(r"^(E\d+)", incident_id)
    return match.group(1) if match else incident_id


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_actions(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml

        return yaml.safe_load(text)
    except ImportError:
        return _parse_simple_actions_yaml(text)


def _parse_simple_actions_yaml(text: str) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("- name:"):
            if current:
                actions.append(current)
            current = {"name": line.split(":", 1)[1].strip()}
            continue
        if current is None or ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            current[key] = [
                item.strip()
                for item in value.strip("[]").split(",")
                if item.strip()
            ]
        else:
            try:
                current[key] = int(value)
            except ValueError:
                current[key] = value
    if current:
        actions.append(current)
    return actions


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _load_dotenv(path: Path) -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(path)
        return
    except ImportError:
        pass
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    decide_parser = subparsers.add_parser("decide")
    decide_parser.add_argument("--incident", required=True)
    decide_parser.add_argument("--history", default="data-pack/incidents_history.json")
    decide_parser.add_argument("--actions", default="data-pack/actions.yaml")
    decide_parser.add_argument("--artifacts-dir", default=str(DEFAULT_ARTIFACTS_DIR))
    decide_parser.add_argument("--model", default=DEFAULT_MODEL)
    decide_parser.add_argument("--llm-mode", choices=["auto", "required", "off"], default="auto")
    args = parser.parse_args()

    if args.command != "decide":
        parser.print_help()
        return 1

    decision = decide(
        incident_path=Path(args.incident),
        history_path=Path(args.history),
        actions_path=Path(args.actions),
        artifacts_dir=Path(args.artifacts_dir),
        model=args.model,
        llm_mode=args.llm_mode,
    )
    print(json.dumps(decision, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
