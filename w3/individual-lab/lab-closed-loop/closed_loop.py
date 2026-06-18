#!/usr/bin/env python3
"""Ronki closed-loop auto-remediation orchestrator."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import requests
import yaml

from engine.logger import JsonLogger
from engine.metrics import (
    action_counter,
    blast_radius_gauge,
    circuit_breaker_gauge,
    mutex_gauge,
    start_metrics_server,
    verify_status_gauge,
)
from engine.safety import BlastRadiusGuard, CircuitBreaker
from engine.verify import verify_service

log = JsonLogger()

_service_locks: dict[str, threading.Lock] = {}
_locks_meta = threading.Lock()


def service_lock(service: str) -> threading.Lock:
    with _locks_meta:
        if service not in _service_locks:
            _service_locks[service] = threading.Lock()
        return _service_locks[service]


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML object")
    return data


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def require_config(config: dict[str, Any], keys: list[str]) -> None:
    missing = [key for key in keys if key not in config]
    if missing:
        raise ValueError(f"Missing config keys: {', '.join(missing)}")


def resolve_path(config_dir: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (config_dir / path).resolve()


def fetch_active_alerts(alertmanager_url: str) -> list[dict[str, Any]]:
    try:
        response = requests.get(
            f"{alertmanager_url}/api/v2/alerts",
            params={"active": "true", "silenced": "false", "inhibited": "false"},
            timeout=5,
        )
        response.raise_for_status()
        alerts = response.json()
        if not isinstance(alerts, list):
            return []
        return alerts
    except requests.RequestException as exc:
        log.error(
            "ALERTMANAGER_FETCH_ERROR",
            action="poll_alertmanager",
            result="error",
            error=str(exc),
        )
        return []


def is_firing(alert: dict[str, Any]) -> bool:
    return alert.get("status", {}).get("state", "active") in {"active", "firing"}


def alert_labels(alert: dict[str, Any]) -> dict[str, str]:
    labels = alert.get("labels", {})
    return labels if isinstance(labels, dict) else {}


def alert_service(alert: dict[str, Any]) -> str:
    labels = alert_labels(alert)
    return labels.get("service") or labels.get("job") or "unknown"


def validate_runbook(
    runbook: str,
    config: dict[str, Any],
    alertname: str,
    raw_decision: Any,
) -> bool:
    registry = set(config.get("runbook_registry", []))
    if runbook in registry:
        return True
    log.error(
        "DECISION_VALIDATION_FAILED",
        action="escalate_no_auto_action",
        result="rejected",
        bad_runbook=runbook,
        alertname=alertname,
        raw_decision=raw_decision,
    )
    return False


def bash_executable() -> str:
    return shutil.which("bash") or "/bin/bash"


def run_runbook(
    script: Path,
    service: str,
    *,
    dry_run: bool,
    timeout_s: int,
    extra_args: list[str] | None = None,
) -> bool:
    cmd = [bash_executable(), str(script), "--service", service]
    if extra_args:
        cmd.extend(extra_args)
    if dry_run:
        cmd.append("--dry-run")

    log.info(
        "RUNBOOK_EXEC",
        service=service,
        action=script.name,
        result="started",
        script=str(script),
        dry_run=dry_run,
        extra_args=extra_args or [],
    )

    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        log.error(
            "RUNBOOK_TIMEOUT",
            service=service,
            action=script.name,
            result="timeout",
            script=str(script),
            timeout_s=timeout_s,
        )
        return False

    ok = completed.returncode == 0
    log.info(
        "RUNBOOK_RESULT",
        service=service,
        action=script.name,
        result="success" if ok else "fail",
        script=str(script),
        returncode=completed.returncode,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
    )
    return ok


def selected_runbook(alertname: str, config: dict[str, Any]) -> str | None:
    if alertname in config.get("multi_step_map", {}):
        return config["multi_step_map"][alertname][0]["runbook"]
    return config.get("runbook_map", {}).get(alertname)


def run_transaction(
    alertname: str,
    service: str,
    config: dict[str, Any],
    config_dir: Path,
    timeout_s: int,
) -> bool:
    completed_steps: list[dict[str, Any]] = []
    steps = config.get("multi_step_map", {}).get(alertname, [])
    rollbacks = config.get("multi_step_rollback_map", {}).get(alertname, [])

    for step in steps:
        runbook = step["runbook"]
        if not validate_runbook(runbook, config, alertname, raw_decision=step):
            return False
        ok = run_runbook(
            resolve_path(config_dir, runbook),
            service,
            dry_run=False,
            timeout_s=timeout_s,
            extra_args=list(step.get("args", [])),
        )
        if ok:
            completed_steps.append(step)
            log.info(
                "TRANSACTIONAL_STEP",
                service=service,
                action=step["name"],
                result="success",
                step=step["name"],
            )
            continue

        log.error(
            "TRANSACTIONAL_STEP_FAIL",
            service=service,
            action=step["name"],
            result="fail",
            step=step["name"],
            completed_before_failure=[item["name"] for item in completed_steps],
        )
        rollback_completed_steps(
            alertname, service, config, config_dir, timeout_s, rollbacks, completed_steps
        )
        return False

    return True


def rollback_completed_steps(
    alertname: str,
    service: str,
    config: dict[str, Any],
    config_dir: Path,
    timeout_s: int,
    rollbacks: list[dict[str, Any]],
    completed_steps: list[dict[str, Any]],
) -> None:
    rollback_slice = rollbacks[: len(completed_steps)]
    rolled_back: list[str] = []

    for rollback in reversed(rollback_slice):
        runbook = rollback["runbook"]
        if not validate_runbook(runbook, config, alertname, raw_decision=rollback):
            continue
        log.warning(
            "TRANSACTIONAL_ROLLBACK_STEP",
            service=service,
            action=rollback["name"],
            result="started",
            step=rollback["name"],
        )
        run_runbook(
            resolve_path(config_dir, runbook),
            service,
            dry_run=False,
            timeout_s=timeout_s,
            extra_args=list(rollback.get("args", [])),
        )
        rolled_back.append(rollback["name"])

    log.info(
        "TRANSACTIONAL_ROLLBACK_COMPLETE",
        service=service,
        action="transactional_rollback",
        result="complete",
        rolled_back=rolled_back,
    )


def rollback(
    alertname: str,
    service: str,
    runbook: str,
    config: dict[str, Any],
    config_dir: Path,
    timeout_s: int,
) -> None:
    rollback_runbook = config.get("rollback_map", {}).get(alertname, runbook)
    if not validate_runbook(
        rollback_runbook,
        config,
        alertname,
        raw_decision=rollback_runbook,
    ):
        return
    log.warning(
        "ROLLBACK_TRIGGERED",
        service=service,
        action=Path(rollback_runbook).name,
        result="started",
        rollback_runbook=rollback_runbook,
    )
    ok = run_runbook(
        resolve_path(config_dir, rollback_runbook),
        service,
        dry_run=False,
        timeout_s=timeout_s,
    )
    log.info(
        "ROLLBACK_EXECUTED",
        service=service,
        action=Path(rollback_runbook).name,
        result="success" if ok else "fail",
        rollback_runbook=rollback_runbook,
    )


def handle_failure(
    service: str,
    action: str,
    breaker: CircuitBreaker,
) -> None:
    opened = breaker.record_failure()
    if opened:
        circuit_breaker_gauge.labels(service=service).set(1)
        log.error(
            "CIRCUIT_BREAKER_HALT",
            service=service,
            action=action,
            result="halt",
            consecutive_failures=breaker.failures,
            threshold=breaker.threshold,
            message="Automation halted. Manual intervention required.",
        )


def process_alert(
    alert: dict[str, Any],
    config: dict[str, Any],
    config_dir: Path,
    baseline: dict[str, Any],
    guard: BlastRadiusGuard,
    breaker: CircuitBreaker,
    global_dry_run: bool,
) -> None:
    labels = alert_labels(alert)
    alertname = labels.get("alertname", "")
    service = alert_service(alert)
    severity = labels.get("severity", "")

    log.info(
        "ALERT_DETECTED",
        service=service,
        action="detect",
        result="detected",
        alertname=alertname,
        severity=severity,
    )

    if breaker.is_open():
        log.error(
            "CIRCUIT_BREAKER_HALT",
            service=service,
            action="circuit_breaker",
            result="halt",
            message="Circuit open; skipping alert.",
        )
        return

    runbook = selected_runbook(alertname, config)
    if not runbook:
        log.warning(
            "NO_RUNBOOK",
            service=service,
            action="decide",
            result="skipped",
            alertname=alertname,
        )
        return

    raw_decision = {"alertname": alertname, "runbook": runbook}
    if not validate_runbook(runbook, config, alertname, raw_decision):
        return

    log.info(
        "DECIDE_RUNBOOK",
        service=service,
        action=Path(runbook).name,
        result="selected",
        alertname=alertname,
        runbook=runbook,
    )

    ok, reason = guard.check(service, runbook)
    if not ok:
        log.warning(
            "BLAST_RADIUS_EXCEEDED",
            service=service,
            action=Path(runbook).name,
            result="skipped",
            reason=reason,
        )
        return

    log.info(
        "BLAST_RADIUS_OK",
        service=service,
        action=Path(runbook).name,
        result="pass",
        remaining_global_actions=guard.remaining_global_actions(),
    )

    lock = service_lock(service)
    if not lock.acquire(blocking=False):
        log.warning(
            "SERVICE_LOCK_BUSY",
            service=service,
            action=Path(runbook).name,
            result="skipped",
            message="Another remediation is active for this service.",
        )
        return

    mutex_gauge.labels(service=service).set(1)
    try:
        process_alert_locked(
            alertname,
            service,
            runbook,
            config,
            config_dir,
            baseline,
            guard,
            breaker,
            global_dry_run,
        )
    finally:
        mutex_gauge.labels(service=service).set(0)
        lock.release()


def process_alert_locked(
    alertname: str,
    service: str,
    runbook: str,
    config: dict[str, Any],
    config_dir: Path,
    baseline: dict[str, Any],
    guard: BlastRadiusGuard,
    breaker: CircuitBreaker,
    global_dry_run: bool,
) -> None:
    timeout_s = int(config["runbook_timeout_seconds"])
    runbook_path = resolve_path(config_dir, runbook)

    dry_run_ok = run_runbook(
        runbook_path,
        service,
        dry_run=True,
        timeout_s=timeout_s,
    )
    if not dry_run_ok:
        log.error(
            "DRY_RUN_FAIL",
            service=service,
            action=Path(runbook).name,
            result="fail",
            runbook=runbook,
        )
        return

    log.info(
        "DRY_RUN_PASS",
        service=service,
        action=Path(runbook).name,
        result="success",
        runbook=runbook,
    )

    if global_dry_run:
        action_counter.labels(service=service, runbook=runbook, outcome="dry_run").inc()
        log.info(
            "GLOBAL_DRY_RUN_SKIP",
            service=service,
            action=Path(runbook).name,
            result="skipped",
            message="--dry-run set; no real action executed.",
        )
        return

    guard.record(service, runbook)
    blast_radius_gauge.labels(service=service).set(guard.remaining_global_actions())

    if alertname in config.get("multi_step_map", {}):
        action_ok = run_transaction(alertname, service, config, config_dir, timeout_s)
    else:
        action_ok = run_runbook(
            runbook_path,
            service,
            dry_run=False,
            timeout_s=timeout_s,
        )

    if not action_ok:
        action_counter.labels(service=service, runbook=runbook, outcome="fail").inc()
        log.error(
            "ACTION_EXEC_FAIL",
            service=service,
            action=Path(runbook).name,
            result="fail",
            runbook=runbook,
        )
        handle_failure(service, Path(runbook).name, breaker)
        return

    log.info(
        "ACTION_EXECUTED",
        service=service,
        action=Path(runbook).name,
        result="success",
        runbook=runbook,
    )

    verify_status_gauge.labels(service=service, runbook=runbook).set(2)
    verify_ok = verify_service(config["prometheus_url"], service, baseline)

    if verify_ok:
        verify_status_gauge.labels(service=service, runbook=runbook).set(1)
        action_counter.labels(service=service, runbook=runbook, outcome="success").inc()
        breaker.record_success()
        circuit_breaker_gauge.labels(service=service).set(0)
        log.info(
            "ACTION_SUCCESS",
            service=service,
            action=Path(runbook).name,
            result="success",
            alertname=alertname,
            runbook=runbook,
        )
        return

    verify_status_gauge.labels(service=service, runbook=runbook).set(0)
    action_counter.labels(service=service, runbook=runbook, outcome="rollback").inc()
    rollback(alertname, service, runbook, config, config_dir, timeout_s)
    handle_failure(service, Path(runbook).name, breaker)


def alert_key(alert: dict[str, Any]) -> str:
    fingerprint = alert.get("fingerprint")
    if fingerprint:
        return str(fingerprint)
    labels = alert_labels(alert)
    return "|".join(
        [
            labels.get("alertname", ""),
            labels.get("service", ""),
            str(alert.get("startsAt", "")),
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Ronki closed-loop orchestrator")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config_dir = config_path.parent
    config = load_yaml(config_path)
    require_config(
        config,
        [
            "alertmanager_url",
            "prometheus_url",
            "poll_interval_seconds",
            "runbook_timeout_seconds",
            "baseline_path",
            "runbook_map",
            "runbook_registry",
            "blast_radius",
            "circuit_breaker",
        ],
    )

    baseline = load_json(resolve_path(config_dir, config["baseline_path"]))
    blast_config = config["blast_radius"]
    breaker_config = config["circuit_breaker"]
    guard = BlastRadiusGuard(
        max_actions_per_minute=int(blast_config["max_actions_per_minute"]),
        max_restarts_per_service_per_hour=int(
            blast_config["max_restarts_per_service_per_hour"]
        ),
    )
    breaker = CircuitBreaker(
        threshold=int(breaker_config["consecutive_failure_threshold"])
    )

    metrics_started = start_metrics_server(int(config.get("metrics_port", 9100)))
    log.info(
        "ORCHESTRATOR_START",
        action="startup",
        result="success",
        config=str(config_path),
        dry_run=args.dry_run,
        metrics_started=metrics_started,
    )

    seen: set[str] = set()
    max_workers = max(2, len(config.get("runbook_map", {})))
    executor = ThreadPoolExecutor(max_workers=max_workers)

    try:
        while True:
            if breaker.is_open():
                log.error(
                    "CIRCUIT_BREAKER_HALT",
                    action="circuit_breaker",
                    result="halt",
                    message="Circuit open; polling paused.",
                )
                time.sleep(int(config["poll_interval_seconds"]))
                continue

            alerts = [alert for alert in fetch_active_alerts(config["alertmanager_url"]) if is_firing(alert)]
            for alert in alerts:
                key = alert_key(alert)
                if key in seen:
                    continue
                seen.add(key)
                executor.submit(
                    process_alert,
                    alert,
                    config,
                    config_dir,
                    baseline,
                    guard,
                    breaker,
                    args.dry_run,
                )

            if len(seen) > 1000:
                seen.clear()

            time.sleep(int(config["poll_interval_seconds"]))
    except KeyboardInterrupt:
        log.info("ORCHESTRATOR_STOP", action="shutdown", result="interrupted")
        return 0
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


if __name__ == "__main__":
    sys.exit(main())
