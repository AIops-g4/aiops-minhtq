# Runtime Contracts

## Orchestrator CLI

Primary command:

```powershell
uv run python closed_loop.py --config config.yaml
```

The orchestrator must also support:

```powershell
uv run python closed_loop.py --config config.yaml --dry-run
```

Orchestrator-level `--dry-run` disables all real action execution. It may still
poll, decide, validate, check safety, call runbook dry-run, and log what would
happen.

## Config Contract

`config.yaml` should include at minimum:

```yaml
alertmanager_url: "http://localhost:9093"
prometheus_url: "http://localhost:9090"
poll_interval_seconds: 15
runbook_timeout_seconds: 30
baseline_path: "data-pack/data/baseline.json"

runbook_map:
  HighLatency: "runbooks/restart_service.sh"
  HighErrorRate: "runbooks/clear_cache.sh"
  InstanceDown: "runbooks/restart_service.sh"

rollback_map:
  HighLatency: "runbooks/restart_service.sh"
  HighErrorRate: "runbooks/restart_service.sh"
  InstanceDown: "runbooks/restart_service.sh"

runbook_registry:
  - "runbooks/restart_service.sh"
  - "runbooks/clear_cache.sh"
  - "runbooks/scale_replicas.sh"

blast_radius:
  max_actions_per_minute: 3
  max_restarts_per_service_per_hour: 5

circuit_breaker:
  consecutive_failure_threshold: 3
  reset_mode: manual
```

Paths are relative to the config file location unless documented otherwise.

## Alertmanager Contract

Poll:

```text
GET http://localhost:9093/api/v2/alerts
```

Required parsed fields:

- `alertname` from `labels.alertname`
- `service` from `labels.service`
- `severity` from `labels.severity`
- firing state from the Alertmanager payload

Only firing alerts should trigger remediation.

## Runbook Contract

Each runbook script must accept:

```bash
bash runbooks/<name>.sh --service <service> [--dry-run]
```

Required behavior:

- `--service` receives the short service label, for example `payment-svc`.
- The script maps short service names to Docker containers, for example
  `payment-svc` -> `ronki-payment-svc`.
- `--dry-run` prints the intended action and exits 0 without side effects.
- Real execution performs the action and exits 0 on success.
- Non-zero exit code means action failure.

Minimum runbooks:

- `restart_service.sh`
- `scale_replicas.sh`
- `clear_cache.sh`

## Structured Log Contract

The orchestrator writes one JSON object per line to stdout.

Every event should include at least:

```json
{
  "ts": "2026-06-18T00:00:00Z",
  "event_type": "ACTION_SUCCESS",
  "service": "payment-svc",
  "action": "restart_service",
  "result": "success"
}
```

Important event types:

- `ALERT_DETECTED`
- `DECIDE_RUNBOOK`
- `DECISION_VALIDATION_FAILED`
- `BLAST_RADIUS_OK`
- `BLAST_RADIUS_EXCEEDED`
- `DRY_RUN_PASS`
- `DRY_RUN_FAIL`
- `RUNBOOK_EXEC`
- `RUNBOOK_RESULT`
- `ACTION_EXECUTED`
- `VERIFY_START`
- `VERIFY_SAMPLE`
- `VERIFY_PASS`
- `VERIFY_FAIL`
- `ACTION_SUCCESS`
- `ROLLBACK_TRIGGERED`
- `ROLLBACK_EXECUTED`
- `SERVICE_LOCK_BUSY`
- `CIRCUIT_BREAKER_HALT`

Stress scenario event types:

- `TRANSACTIONAL_STEP`
- `TRANSACTIONAL_STEP_FAIL`
- `TRANSACTIONAL_ROLLBACK_STEP`
- `TRANSACTIONAL_ROLLBACK_COMPLETE`

## Safety Contract

The orchestrator must not execute a real runbook if any of these fail:

- Alert is not firing.
- Runbook is absent from `runbook_registry`.
- Circuit breaker is open.
- Blast-radius limit is exceeded.
- Service lock cannot be acquired.
- Runbook dry-run exits non-zero.

Action or verify failure increments the circuit-breaker failure count.
Decision validation failure does not.
