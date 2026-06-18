# 002 - Retrain, Approval Gate, And Blue-Green Rollout Tasks

## Implementation

- [ ] Add `retrain.py` CLI with `--reference`, `--current`, `--holdout`, and
      threshold options.
- [ ] Reuse drift detection logic from `drift_detector.py`.
- [ ] Stop safely when drift is not detected.
- [ ] Build sliding-window training data from reference plus current rows.
- [ ] Train and register v2 with alias `staging`.
- [ ] Evaluate v1 and v2 on `holdout.csv`.
- [ ] Print the required holdout validation line.
- [ ] Implement the approval prompt exactly enough for acceptance.
- [ ] Promote only after explicit `y` or `Y`.
- [ ] Capture previous production version for rollback.
- [ ] Move `production` alias to the staging version.
- [ ] Call `POST /reload` on `serve.py`.
- [ ] Append structured audit events to `outputs/audit_log.jsonl`.

## Validation

- [ ] Ensure v1 is registered and `serve.py` is running.
- [ ] Run `uv run python retrain.py --reference data-pack/data/baseline.csv --current data-pack/data/drifted.csv --holdout data-pack/data/holdout.csv`.
- [ ] Confirm v2 appears in MLflow.
- [ ] Confirm alias `staging` points to v2 before approval.
- [ ] Reject approval once and confirm `production` remains v1.
- [ ] Approve promotion once and confirm `production` moves to v2.
- [ ] Confirm `/health/active-version` reports v2 after reload.
- [ ] Confirm `outputs/audit_log.jsonl` contains approval and promotion events.

## Documentation

- [ ] In `DESIGN.md`, explain manual approval ownership and timeout policy.
- [ ] In `DESIGN.md`, explain alias-based rollback.
- [ ] In `DESIGN.md`, compare sliding-window training against drift-window-only
      training.
- [ ] In `SUBMIT.md`, explain why blue-green alias swap is safer than replacing
      a model file.
