# 003 - Robustness Stress Scenarios Spec

## Goal

Handle the three required stress scenarios: distinguish data drift from
performance degradation, avoid retrain overfitting, and roll back automatically
when post-deploy precision is unsafe.

## Stress 1: Combined Drift Mode

`drifted.csv` contains both feature distribution shift and a label-based
concept-drift trap. Evidently `DataDriftPreset` can detect feature drift, but
it does not directly detect concept drift.

`drift_detector.py` must support:

```powershell
uv run python drift_detector.py --reference data-pack/data/baseline.csv --current data-pack/data/drifted.csv --check-mode combined --model-uri models:/anomaly-detector@production --labeled-current data-pack/data/drifted.csv
```

Output must include:

```text
Drift score
Perf precision
```

Combined mode triggers when either:

- data drift exceeds threshold, or
- performance precision falls below the configured minimum.

`DESIGN.md` must explain why these two mechanisms detect different failure
modes and include at least one concrete numerical example.

## Stress 2: Retrain Data Selection

Retraining only on the drift window can overfit to the new seven-day regime.
The default strategy must include both the reference baseline and current
drifted data.

Acceptance command:

```powershell
uv run python retrain.py --reference data-pack/data/baseline.csv --current data-pack/data/drifted.csv --holdout data-pack/data/holdout.csv
```

Required output:

```text
Holdout validation — v2 precision: X.XXXX  recall: X.XXXX
```

The precision value must be greater than or equal to v1 precision measured on
the same holdout.

`DESIGN.md` must compare the sliding-window approach against at least one
alternative.

## Stress 3: Post-Deploy Auto-Rollback

After v2 is promoted to `@production`, monitor v2 on:

```text
data-pack/data/post_deploy_eval.csv
```

Run up to 24 polling cycles. Each cycle must print:

```text
post_deploy_monitor Cycle XX/24
```

If v2 precision falls below `0.65`, the pipeline must:

1. Set alias `archived` to v2.
2. Restore alias `production` to v1.
3. Call `POST /reload` on `serve.py`.
4. Append event `auto_rollback_v2_to_v1` to `outputs/audit_log.jsonl`.
5. Print:

   ```text
   Rollback complete. v1 restored to @production. v2 → @archived
   ```

The audit event must include:

- `demoted_version`
- `restored_version`
- `trigger_precision`
- `cycle`

## Acceptance Criteria

- Combined drift mode prints both data drift and performance values.
- Data-only mode does not claim to detect concept drift.
- Retrain command prints holdout precision and recall.
- v2 holdout precision is at least v1 holdout precision.
- Post-deploy monitoring prints cycle lines.
- Auto-rollback restores the previous production version when precision is too
  low.
- Audit log contains `auto_rollback_v2_to_v1` with required fields.
- `DESIGN.md` includes real run numbers for all three stress scenarios when
  available.
