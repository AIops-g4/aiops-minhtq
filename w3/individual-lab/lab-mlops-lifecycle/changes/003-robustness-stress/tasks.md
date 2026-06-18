# 003 - Robustness Stress Scenarios Tasks

## Implementation

- [ ] Add `--check-mode data|performance|combined` to `drift_detector.py`.
- [ ] Add `--model-uri` and `--labeled-current` for performance checks.
- [ ] Compute precision and recall from labeled current data.
- [ ] Print `Drift score` in data and combined modes.
- [ ] Print `Perf precision` in performance and combined modes.
- [ ] Ensure combined mode triggers when either data drift or performance
      degradation is true.
- [ ] Ensure data-only mode does not report performance precision.
- [ ] Enforce sliding-window retrain data in `retrain.py`.
- [ ] Compare v1 and v2 on `holdout.csv`.
- [ ] Block or warn on promotion when v2 holdout precision is below v1.
- [ ] Add `--post-deploy-eval` to `retrain.py`.
- [ ] Implement 24-cycle post-deploy monitor.
- [ ] Trigger rollback when precision falls below `0.65`.
- [ ] Move v2 to alias `archived` and restore v1 to `production`.
- [ ] Reload `serve.py` after rollback.
- [ ] Append `auto_rollback_v2_to_v1` audit event with required fields.

## Validation

- [ ] Run combined drift command and confirm output contains `Drift score`.
- [ ] Confirm combined drift output contains `Perf precision`.
- [ ] Run data-only mode and confirm it does not claim concept-drift detection.
- [ ] Run retrain with `--holdout` and capture v1/v2 precision values.
- [ ] Confirm v2 holdout precision is greater than or equal to v1.
- [ ] Run retrain with `--post-deploy-eval`.
- [ ] Confirm terminal prints `post_deploy_monitor Cycle XX/24`.
- [ ] Force or observe rollback when precision is below `0.65`.
- [ ] Confirm final rollback line is printed.
- [ ] Confirm `outputs/audit_log.jsonl` contains `auto_rollback_v2_to_v1`.
- [ ] Confirm audit event has `demoted_version`, `restored_version`,
      `trigger_precision`, and `cycle`.

## Documentation

- [ ] In `DESIGN.md`, explain why combined mode is necessary.
- [ ] In `DESIGN.md`, include one numerical example for data drift versus
      performance degradation.
- [ ] In `DESIGN.md`, document sliding-window data selection and alternatives.
- [ ] In `DESIGN.md`, document rollback threshold `0.65` and authority.
- [ ] In `SUBMIT.md`, answer what happens when v2 performs worse than v1.
- [ ] In `SUBMIT.md`, explain data drift versus concept drift.
- [ ] In `SUBMIT.md`, describe the metric and threshold for automated
      approval.
