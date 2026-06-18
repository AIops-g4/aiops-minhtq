# 001 - Core Closed-Loop Orchestrator Spec

## Goal

Create a runnable orchestrator that detects firing Alertmanager alerts, maps
them to registered runbooks, dry-runs the selected runbook, and logs each step
as structured JSON.

This increment proves the learner can connect the live stack to remediation
logic without executing unsafe actions.

## Inputs

The orchestrator reads:

- `config.yaml`
- Alertmanager API at `alertmanager_url`
- Runbook scripts under `runbooks/`

The config must include:

- `alertmanager_url`
- `poll_interval_seconds`
- `runbook_timeout_seconds`
- `runbook_map`
- `runbook_registry`

## Behavior

1. Parse CLI args: `--config` and optional `--dry-run`.
2. Load YAML config and resolve paths relative to the config file.
3. Poll `GET /api/v2/alerts` every `poll_interval_seconds`.
4. Keep only firing alerts.
5. Parse `alertname`, `service`, and `severity`.
6. Select runbook from `runbook_map`.
7. Validate selected runbook against `runbook_registry`.
8. Execute runbook dry-run:

   ```bash
   bash <runbook> --service <service> --dry-run
   ```

9. Log all major steps as one JSON object per line.

If orchestrator-level `--dry-run` is set, log that real execution would be
skipped. Real runbook execution can be added in the next increment.

## Runbooks

Minimum scripts:

- `runbooks/restart_service.sh`
- `runbooks/clear_cache.sh`
- `runbooks/scale_replicas.sh`

All scripts must:

- Accept `--service <service>`.
- Accept `--dry-run`.
- Exit 0 for successful dry-run.
- Print a human-readable intended command during dry-run.
- Map short service labels to `ronki-<service>` for Docker operations.

## Required Log Events

- `ALERT_DETECTED`
- `DECIDE_RUNBOOK`
- `DECISION_VALIDATION_FAILED`
- `DRY_RUN_PASS`
- `DRY_RUN_FAIL`
- `RUNBOOK_EXEC`
- `RUNBOOK_RESULT`

`DECISION_VALIDATION_FAILED` must include:

- `bad_runbook`
- `alertname`
- `raw_decision`
- `action: "escalate_no_auto_action"`

No subprocess may be spawned for an invalid runbook.

## Acceptance Criteria

- `uv run python closed_loop.py --help` succeeds.
- Config loading fails with a clear message if required keys are missing.
- All three runbooks pass dry-run commands.
- A firing alert produces `ALERT_DETECTED`, `DECIDE_RUNBOOK`, and
  `DRY_RUN_PASS`.
- Invalid runbook mapping produces `DECISION_VALIDATION_FAILED` and no
  `RUNBOOK_EXEC`.
