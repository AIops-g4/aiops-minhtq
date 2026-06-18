# 003 - Excellent-Level Stress Scenarios Spec

## Goal

Make the orchestrator robust under production-like edge cases: partial
multi-step actions, simultaneous incidents, duplicate alerts, and invalid
decision output.

## Transactional Multi-Step Rollback

Config may include:

```yaml
multi_step_map:
  MultiStepDeploy:
    - name: step-A
      runbook: "runbooks/multi_step_deploy.sh"
      args: ["--step-a"]
    - name: step-B
      runbook: "runbooks/multi_step_deploy.sh"
      args: ["--step-b"]
    - name: step-C
      runbook: "runbooks/multi_step_deploy.sh"
      args: ["--step-c"]

multi_step_rollback_map:
  MultiStepDeploy:
    - name: rollback-A
      runbook: "runbooks/multi_step_deploy.sh"
      args: ["--rollback-a"]
    - name: rollback-B
      runbook: "runbooks/multi_step_deploy.sh"
      args: ["--rollback-b"]
    - name: rollback-C
      runbook: "runbooks/multi_step_deploy.sh"
      args: ["--rollback-c"]
```

Behavior:

- Execute steps in configured order.
- Track only completed steps.
- If step C fails after A and B complete, log `TRANSACTIONAL_STEP_FAIL`.
- Roll back completed steps in reverse order: rollback-B, then rollback-A.
- Log one `TRANSACTIONAL_ROLLBACK_STEP` per rollback script.
- Log `TRANSACTIONAL_ROLLBACK_COMPLETE` with `rolled_back`.
- Do not log `ACTION_SUCCESS` for a failed transaction.

## Concurrent Alert Processing

Behavior:

- Process alerts for different services concurrently.
- Use one non-blocking lock per service.
- If a second alert arrives for a service that is already running a remediation,
  log `SERVICE_LOCK_BUSY` and skip that duplicate action.
- Do not block `payment-svc` remediation because `inventory-svc` is running.

Implementation may use `ThreadPoolExecutor` or worker threads. The per-service
mutex contract is more important than the exact concurrency primitive.

## Decision Validation Defense

Before any dry-run or real runbook execution:

- Validate selected runbook path against `runbook_registry`.
- Reject missing or unregistered paths.
- Log `DECISION_VALIDATION_FAILED` with `bad_runbook`, `alertname`,
  `raw_decision`, and `action: "escalate_no_auto_action"`.
- Do not emit `RUNBOOK_EXEC`.
- Do not spawn a subprocess.
- Do not increment the circuit-breaker failure count.

This applies to both rule-based and optional LLM-based decisions.

## Optional Metrics Exporter

If implementing dashboard support, expose metrics on `localhost:9100` using
`prometheus_client`.

Recommended metrics:

- `closed_loop_actions_total{service,runbook,outcome}`
- `closed_loop_circuit_breaker_state{service}`
- `closed_loop_blast_radius_remaining`
- `closed_loop_mutex_locked{service}`
- `closed_loop_verify_status{service}`

Metrics are useful for Grafana but not required for basic acceptance.

## Acceptance Criteria

- Scenario 4 logs `TRANSACTIONAL_STEP_FAIL`, two rollback steps in reverse
  order, and `TRANSACTIONAL_ROLLBACK_COMPLETE`.
- Scenario 5 processes two different services in parallel and logs
  `SERVICE_LOCK_BUSY` only for duplicate same-service alerts.
- Scenario 6 logs `DECISION_VALIDATION_FAILED` and produces no later
  `RUNBOOK_EXEC` for the invalid decision.
- Circuit breaker state does not change after validation failure.
- `DESIGN.md` explains mutex strategy, rollback order, and validation policy.
- `SUBMIT.md` includes logs for Scenarios 4 through 6 if targeting excellent.
