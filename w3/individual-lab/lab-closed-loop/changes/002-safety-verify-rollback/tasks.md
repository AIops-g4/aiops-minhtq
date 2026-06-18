# 002 - Safety, Verify, Rollback, And Circuit Breaker Tasks

## Implementation

- [x] Extend `config.yaml` with Prometheus, baseline, rollback, blast-radius,
      and circuit-breaker settings.
- [x] Implement in-memory action history for blast-radius checks.
- [x] Log `BLAST_RADIUS_OK` and `BLAST_RADIUS_EXCEEDED`.
- [x] Add real runbook execution after dry-run pass.
- [x] Implement Prometheus query helper with request timeout.
- [x] Load verify thresholds and PromQL templates from `baseline.json`.
- [x] Implement verify loop with timeout, poll interval, and minimum samples.
- [x] Implement rollback selection and rollback execution.
- [x] Track consecutive action or verify failures.
- [x] Open circuit breaker at 3 consecutive failures.
- [x] Make open circuit skip all remediation actions.

## Validation

- [ ] Run Scenario 1: latency fault on `ronki-payment-svc`.
- [ ] Confirm `ACTION_SUCCESS` and three passing verify samples.
- [ ] Run Scenario 2: forced verify failure or killed `ronki-checkout-svc`.
- [ ] Confirm `ROLLBACK_TRIGGERED` and `ROLLBACK_EXECUTED`.
- [ ] Run Scenario 3: three consecutive failures.
- [ ] Confirm `CIRCUIT_BREAKER_HALT` and no further `RUNBOOK_EXEC`.
- [ ] Confirm blast-radius exceed path does not run a real action.

## Documentation

- [x] Fill `DESIGN.md` with decision engine, blast-radius values, verify
      thresholds, and circuit breaker reset policy.
- [x] Fill `SUBMIT.md` with commands, logs, and pass/fail notes for Scenarios 1
      through 3.
