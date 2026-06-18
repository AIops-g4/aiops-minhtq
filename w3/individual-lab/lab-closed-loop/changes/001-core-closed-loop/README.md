# 001 - Core Closed-Loop Orchestrator

This change introduces the minimum working orchestrator and runbook structure.

Scope:

- CLI entry point `closed_loop.py`.
- YAML config loading.
- Alertmanager polling and alert parsing.
- Rule-based alert to runbook decision.
- Runbook registry validation.
- Structured JSON logs.
- Minimum runbook scripts with `--service` and `--dry-run`.

Out of scope:

- Prometheus verify logic.
- Auto-rollback.
- Circuit breaker.
- Concurrent alert processing.
- Multi-step transactional rollback.
- Optional Grafana metrics exporter.
