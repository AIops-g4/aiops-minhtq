# Specs

This directory contains stable project knowledge for the MLOps Lifecycle lab.
It describes what the learner must build, which runtime contracts must remain
stable, and which data and observability surfaces are available.

Feature-specific implementation plans belong under `../changes/`.

## Read Order

1. `system-context.md`
2. `runtime-contracts.md`
3. `data-observability.md`
4. Relevant folder under `../changes/`

## Boundary

Keep in `specs/`:

- Lab objective and high-level MLOps lifecycle architecture.
- Submission structure and public contracts.
- MLflow, FastAPI, Evidently, retrain, audit, and observability contracts.
- Stable dataset names, ports, model names, aliases, and acceptance criteria.

Move to `changes/`:

- Increment-specific implementation plans.
- Task lists.
- Acceptance criteria for a specific capability.
- Notes about implementation order or temporary validation setup.
