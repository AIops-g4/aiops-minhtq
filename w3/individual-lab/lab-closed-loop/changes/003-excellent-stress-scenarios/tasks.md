# 003 - Excellent-Level Stress Scenarios Tasks

## Implementation

- [x] Add optional multi-step deploy config entries.
- [x] Add `runbooks/multi_step_deploy.sh` if targeting Scenario 4.
- [x] Implement transactional step execution.
- [x] Track completed steps and rollback in reverse order.
- [x] Log transactional step and rollback events.
- [x] Add per-service non-blocking lock manager.
- [x] Process different-service alerts concurrently.
- [x] Log `SERVICE_LOCK_BUSY` for duplicate same-service alerts.
- [x] Ensure runbook registry validation runs before every dry-run.
- [x] Ensure validation failure does not increment failure count.
- [x] Optionally expose orchestrator metrics on port 9100.

## Validation

- [ ] Run Scenario 4 and force step C failure.
- [ ] Confirm rollback order is rollback-B then rollback-A.
- [ ] Confirm no `ACTION_SUCCESS` appears for failed transaction.
- [ ] Run concurrent inject on payment and inventory services.
- [ ] Confirm `DRY_RUN_PASS` events are within 1 second of each other.
- [ ] Inject duplicate same-service alert during active remediation.
- [ ] Confirm `SERVICE_LOCK_BUSY`.
- [ ] Add temporary invalid runbook mapping.
- [ ] Confirm `DECISION_VALIDATION_FAILED` and no `RUNBOOK_EXEC`.
- [ ] Confirm circuit breaker counter is unchanged after validation failure.

## Documentation

- [x] Add excellent-level notes to `DESIGN.md` for transactional rollback,
      mutex strategy, and decision validation.
- [x] Add stress scenario logs to `SUBMIT.md` when completed.
