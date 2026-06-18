# Specs

This directory contains stable project knowledge for the Closed-Loop
Auto-Remediation lab. It describes what the learner must build, which runtime
contracts must not change, and which data and observability surfaces are
available.

Feature-specific implementation plans belong under `../changes/`.

## Read Order

1. `system-context.md`
2. `runtime-contracts.md`
3. `observability-data.md`
4. Relevant folder under `../changes/`

## Boundary

Keep in `specs/`:

- Lab objective and high-level closed-loop architecture.
- Submission structure and public contracts.
- Alertmanager, Prometheus, logging, runbook, and config contracts.
- Stable service names, ports, metrics, thresholds, and scenario expectations.

Move to `changes/`:

- Increment-specific implementation plans.
- Task lists.
- Acceptance criteria for a specific capability.
- Notes about implementation order or temporary testing setup.
