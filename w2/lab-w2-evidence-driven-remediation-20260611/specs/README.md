# Specs

This directory contains stable project knowledge for the AIOps remediation lab.
It should describe what the system is, what data exists, and which contracts must
not change during implementation.

Feature-specific plans belong under `changes/`.

## Read Order

1. `system-context.md`
2. `data-model.md`
3. Relevant folder under `../changes/`

## Boundary

Keep in `specs/`:
- Lab objective and high-level engine architecture.
- Input and output contracts.
- Data relationships that apply across all features.
- Constraints from `data-pack/HANDOUT.md`.

Move to `changes/`:
- Feature implementation plans.
- Detector-specific scoring formulas.
- Task lists.
- Acceptance criteria for a specific increment.
