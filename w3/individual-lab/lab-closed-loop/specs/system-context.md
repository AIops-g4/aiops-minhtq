# System Context

## Objective

Build a local closed-loop auto-remediation orchestrator for the Ronki
e-commerce mock stack.

The orchestrator must detect live alerts, choose a remediation action, execute
it safely, verify recovery with Prometheus, and automatically roll back or halt
when recovery is unsafe.

## Runtime Stack

The provided stack in `data-pack/configs/docker-compose.yml` contains:

- Five FastAPI mock services: `frontend`, `api-gateway`, `payment-svc`,
  `inventory-svc`, and `checkout-svc`.
- Prometheus on `localhost:9090`.
- Alertmanager on `localhost:9093`.
- Grafana on `localhost:3000`.
- Loki and Promtail for optional audit log visualization.

Grafana is useful for debugging but is not a grading requirement.

## Closed-Loop Flow

```text
Alertmanager alert
-> detect and parse alert fields
-> decide runbook
-> validate runbook against registry
-> check blast-radius and circuit-breaker state
-> dry-run runbook
-> execute runbook
-> verify metrics in Prometheus
-> log success, rollback, or halt
```

Each action must pass all safety checkpoints before real execution. Missing a
checkpoint means the action must not run.

## Submission Root

The handout calls the learner submission directory `your-name/`. In this repo,
treat `w3/individual-lab/lab-closed-loop/` as the submission root unless the
user explicitly asks for a separate named directory.

Required learner-owned files:

```text
closed_loop.py
config.yaml
runbooks/restart_service.sh
runbooks/scale_replicas.sh
runbooks/clear_cache.sh
DESIGN.md
SUBMIT.md
```

`data-pack/` is provided input material and should remain stable during learner
implementation.

## Non-Negotiable Constraints

- Poll Alertmanager API, not static fixture files.
- Verify via Prometheus queries, not only process exit codes.
- Use YAML config for runbook maps, safety limits, and paths.
- Use structured JSON logs to stdout.
- Always dry-run a runbook before real execution.
- Auto-rollback on verify failure.
- Open the circuit breaker after 3 consecutive action or verify failures.
- Prevent concurrent runbooks for the same service.
- Reject unregistered runbooks before any subprocess is spawned.

## Decision Engine Default

Use a rule-based decision engine by default:

```python
RUNBOOK_MAP = {
    "HighLatency": "runbooks/restart_service.sh",
    "HighErrorRate": "runbooks/clear_cache.sh",
    "InstanceDown": "runbooks/restart_service.sh",
}
```

LLM-based decision is optional and should only be implemented if requested.
Rule-based decision can earn full credit when it is deterministic, validated,
and defended in `DESIGN.md`.
