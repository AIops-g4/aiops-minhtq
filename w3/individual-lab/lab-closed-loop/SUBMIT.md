# SUBMIT.md - Closed-Loop Auto-Remediation Results

## Environment

- Decision engine: rule-based
- Config: `config.yaml`
- Baseline: `data-pack/data/baseline.json`
- Orchestrator command:

```bash
uv run python closed_loop.py --config config.yaml
```

## Scenario 1 - Action Succeeds

Inject command:

```bash
bash data-pack/scripts/inject_fault.sh latency ronki-payment-svc 500ms
```

Expected key events:

```text
ALERT_DETECTED
DECIDE_RUNBOOK
BLAST_RADIUS_OK
DRY_RUN_PASS
ACTION_EXECUTED
VERIFY_PASS
ACTION_SUCCESS
```

Result: pending live stack run.

## Scenario 2 - Action Fails, Rollback Triggers

Inject command:

```bash
bash data-pack/scripts/inject_fault.sh kill ronki-checkout-svc
```

To force verify failure during rollback testing, temporarily lower
`verify_thresholds.latency_p99_max_ms` in the baseline copy used by the run.

Expected key events:

```text
ALERT_DETECTED
DECIDE_RUNBOOK
BLAST_RADIUS_OK
DRY_RUN_PASS
ACTION_EXECUTED
VERIFY_FAIL
ROLLBACK_TRIGGERED
ROLLBACK_EXECUTED
```

Result: pending live stack run.

## Scenario 3 - Circuit Breaker

Setup: run three consecutive failure cases by keeping verify intentionally
failing.

Expected key events:

```text
VERIFY_FAIL
ROLLBACK_TRIGGERED
VERIFY_FAIL
ROLLBACK_TRIGGERED
VERIFY_FAIL
ROLLBACK_TRIGGERED
CIRCUIT_BREAKER_HALT
```

Result: pending live stack run.

## Stress Scenarios

Excellent-level support has been implemented for:

- Scenario 4: transactional rollback events.
- Scenario 5: per-service lock and `SERVICE_LOCK_BUSY`.
- Scenario 6: `DECISION_VALIDATION_FAILED` before subprocess execution.

Result: pending live stack run.
