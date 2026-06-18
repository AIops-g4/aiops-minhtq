# DESIGN.md - Ronki Closed-Loop Orchestrator

## 1. Decision Engine

Chosen engine: rule-based.

The Ronki lab has a small fixed alert surface: `HighLatency`, `HighErrorRate`,
and `InstanceDown`. A rule-based map is deterministic, fast, cheap, and easier
to audit than an LLM call. This is the safer default for auto-remediation because
the same alert always maps to the same reviewed runbook.

Trade-off: rule-based logic requires manual updates when new alert types are
introduced. An LLM could help when alert context is ambiguous, but it must still
be guarded by a runbook registry and confidence threshold. This implementation
keeps the registry validation path so an invalid or hallucinated runbook is
rejected before any subprocess is spawned.

Configured mapping:

```yaml
HighLatency: "runbooks/restart_service.sh"
HighErrorRate: "runbooks/clear_cache.sh"
InstanceDown: "runbooks/restart_service.sh"
```

## 2. Blast-Radius Config

```yaml
blast_radius:
  max_actions_per_minute: 3
  max_restarts_per_service_per_hour: 5
```

`max_actions_per_minute: 3` allows the orchestrator to react quickly during a
small cascade without restarting the full five-service stack at once.

`max_restarts_per_service_per_hour: 5` prevents an endless restart loop for a
single unhealthy service. If a service needs more than five automated restarts in
an hour, the likely problem is not recoverable by repeated restart and should be
escalated.

When a limit is hit, the orchestrator logs `BLAST_RADIUS_EXCEEDED` and does not
execute the action.

## 3. Verify Step

The verify step reads `data-pack/data/baseline.json` and queries Prometheus.

Metrics checked:

- p99 latency: must be `<= 500 ms`
- error rate: must be `<= 10.0%`
- `up`: must be `>= 1`

Timeout and sampling:

- `verify_timeout_seconds: 60`
- `verify_poll_interval_seconds: 10`
- `verify_min_samples: 3`

Three consecutive passing samples are required. A single passing sample is not
enough because Prometheus scrapes every 10 seconds and the first post-restart
sample can be misleading.

## 4. Circuit Breaker Reset

Reset mode: manual.

The circuit opens after three consecutive action or verify failures. At that
point the automation has already tried and failed repeatedly, so continuing to
act can make the incident worse. Manual reset means an operator reviews the logs,
fixes the root issue, and restarts:

```bash
uv run python closed_loop.py --config config.yaml
```

Validation failures such as an unregistered runbook do not increment the circuit
breaker because no action was attempted.

## 5. Excellent-Level Guards

Concurrency: one non-blocking lock is maintained per service. Different services
can remediate in parallel, while duplicate alerts for the same service log
`SERVICE_LOCK_BUSY`.

Transactional rollback: multi-step actions record completed steps. If a later
step fails, only completed steps are rolled back in reverse order.

Decision validation: every selected runbook must exist in `runbook_registry`.
Invalid decisions log `DECISION_VALIDATION_FAILED` and return before dry-run or
real execution.
