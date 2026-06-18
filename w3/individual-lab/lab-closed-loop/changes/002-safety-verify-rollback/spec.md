# 002 - Safety, Verify, Rollback, And Circuit Breaker Spec

## Goal

Complete the core lab requirement: every action must be safe to execute, verified
against Prometheus, rolled back on failure, and halted after repeated failures.

## Inputs

Additional config:

- `prometheus_url`
- `baseline_path`
- `rollback_map`
- `blast_radius.max_actions_per_minute`
- `blast_radius.max_restarts_per_service_per_hour`
- `circuit_breaker.consecutive_failure_threshold`
- `circuit_breaker.reset_mode`

Baseline source:

```text
data-pack/data/baseline.json
```

## Blast-Radius Behavior

Track recent actions in memory:

- Total actions across all services during the last 60 seconds.
- Restart actions per service during the last hour.

If either limit is exceeded:

- Log `BLAST_RADIUS_EXCEEDED`.
- Do not dry-run or execute a real action.
- Do not increment the circuit-breaker failure count.

If within limits:

- Log `BLAST_RADIUS_OK`.

## Execution Behavior

For each valid firing alert:

1. Confirm circuit breaker is closed.
2. Confirm blast-radius permits the action.
3. Run selected runbook with `--dry-run`.
4. If dry-run passes and orchestrator is not in `--dry-run`, execute real
   runbook.
5. Log `ACTION_EXECUTED` only after the real runbook exits 0.
6. Treat non-zero runbook exit or timeout as action failure.

## Verify Behavior

After successful real execution:

1. Log `VERIFY_START`.
2. Query Prometheus for `latency_p99`, `error_rate_pct`, and `up` using query
   templates from `baseline.json`.
3. Poll for up to `verify_timeout_seconds`.
4. Wait `verify_poll_interval_seconds` between samples.
5. Require `verify_min_samples` passing samples.
6. A passing sample must meet:
   - p99 latency <= `latency_p99_max_ms`
   - error rate <= `error_rate_max_pct`
   - up == `up_required`

If enough samples pass:

- Log `VERIFY_PASS`.
- Log `ACTION_SUCCESS`.
- Reset consecutive failure count.

If timeout expires or samples fail:

- Log `VERIFY_FAIL`.
- Trigger rollback.

## Rollback Behavior

On action failure or verify failure:

1. Increment consecutive failure count.
2. Select rollback runbook from `rollback_map`, defaulting to the original
   runbook when no explicit mapping exists.
3. Log `ROLLBACK_TRIGGERED`.
4. Execute rollback runbook with the same service.
5. Log `ROLLBACK_EXECUTED` or rollback failure details.

Rollback should be attempted even if verify fails after the original action
exited 0.

## Circuit Breaker Behavior

When consecutive failure count reaches the configured threshold:

- Set circuit state to open.
- Log `CIRCUIT_BREAKER_HALT`.
- Stop executing actions until the process is manually restarted.

Manual reset is the default. Do not implement automatic reset unless the user
explicitly asks for it.

## Acceptance Criteria

- Scenario 1 logs `ACTION_SUCCESS` after latency recovery.
- Scenario 2 logs `VERIFY_FAIL`, `ROLLBACK_TRIGGERED`, and
  `ROLLBACK_EXECUTED`.
- Scenario 3 logs `CIRCUIT_BREAKER_HALT` after the third consecutive failure.
- No real action runs without dry-run success and blast-radius approval.
- `DESIGN.md` answers all four required design questions with concrete values.
- `SUBMIT.md` includes representative logs from all three scenarios.
