# 001 - Core Closed-Loop Orchestrator Tasks

## Implementation

- [x] Add `config.yaml` with Alertmanager URL, runbook map, registry, and basic
      timeouts.
- [x] Add `closed_loop.py` CLI with `--config` and `--dry-run`.
- [x] Implement YAML config loading with paths resolved from the config file.
- [x] Implement Alertmanager polling with request timeout.
- [x] Parse firing alerts into alertname, service, severity, and raw payload.
- [x] Implement rule-based decision from alertname to runbook path.
- [x] Validate decisions against `runbook_registry`.
- [x] Add JSON-line structured logging helper.
- [x] Add runbook subprocess dry-run helper with timeout.
- [x] Add `runbooks/restart_service.sh`.
- [x] Add `runbooks/clear_cache.sh`.
- [x] Add `runbooks/scale_replicas.sh`.

## Validation

- [x] Run `uv run python closed_loop.py --help`.
- [x] Run each runbook with `--dry-run`.
- [ ] Start the stack and confirm Alertmanager health.
- [ ] Inject a latency fault and confirm alert detection.
- [ ] Confirm invalid runbook mapping logs `DECISION_VALIDATION_FAILED`.
- [ ] Confirm invalid mapping does not produce `RUNBOOK_EXEC`.

## Documentation

- [x] Document rule-based decision choice in `DESIGN.md`.
- [x] Document dry-run behavior and sample logs in `SUBMIT.md`.
