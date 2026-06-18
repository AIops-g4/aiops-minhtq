# Data And Observability

## Provided Data

All datasets live under:

```text
data-pack/data/
```

## Dataset Contract

`baseline.csv`:

- 4320 rows.
- Represents 30 days of normal operation.
- One row every 10 minutes.
- Feature columns:
  - `latency_p99`
  - `error_rate`
  - `rps`
- Approximate distribution:
  - latency around 120 ms.
  - error rate around 0.8%.
  - traffic around 450 requests/sec.

`drifted.csv`:

- 1008 rows.
- Represents 7 days after a traffic campaign and integration changes.
- Same feature schema.
- Approximate distribution shift:
  - latency mean rises about 30%.
  - error rate roughly doubles.
  - traffic rises about 40%.
- Includes a concept-drift trap through label changes for stress testing.

`holdout.csv`:

- 500 labeled rows from the old pattern.
- Used to confirm v2 does not regress against the old regime.
- Acceptance requires v2 precision on this file to be at least v1 precision on
  the same holdout.

`post_deploy_eval.csv`:

- 200 labeled rows.
- Used after v2 promotion.
- If v2 precision falls below the rollback threshold within 24 polling cycles,
  rollback must restore v1.

Regenerate deterministic data:

```powershell
cd data-pack
uv run python data/generate_data.py
```

## Feature Columns

The model and drift checks should use only:

```text
latency_p99,error_rate,rps
```

The following columns are metadata or labels when present:

- `timestamp`
- `anomaly_label`

Never train IsolationForest directly on `timestamp` or `anomaly_label`.

## Drift Measurement

The lab's default data-drift mechanism is Evidently `DataDriftPreset`.

Expected learner-level API shape:

```python
detect_drift(reference_df, current_df, threshold) -> DriftResult
```

`DriftResult` should include:

- `score`
- `is_drift`
- `report_path`

Use the same feature column list for reference and current data. A threshold
around `0.15` is acceptable only when it is supported by measured no-drift and
drifted runs.

## Performance Measurement

Because IsolationForest returns `1` for inliers and `-1` for anomalies, code
should normalize predictions before computing precision and recall against
`anomaly_label`.

Document the chosen mapping in code. A common mapping is:

```text
prediction == -1 -> anomaly label 1
prediction ==  1 -> normal label 0
```

Performance checks are required for combined mode and post-deploy rollback.

## Observability Surfaces

Grafana dashboard:

```text
http://localhost:3000
```

Prometheus:

```text
http://localhost:9090
```

Pushgateway:

```text
http://localhost:9091
```

MLflow:

```text
http://localhost:5000
```

Grafana is useful for debugging trends, but acceptance is based on scripts,
terminal output, MLflow registry behavior, saved reports, and audit logs.

## Metrics To Emit When Practical

Batch jobs can push:

- `mlops_drift_score`
- `mlops_drift_detected`
- `mlops_retrain_count`
- `mlops_auto_rollback_count`
- `mlops_model_precision`
- `mlops_model_recall`
- `mlops_production_version`
- `mlops_staging_version`

The FastAPI server can expose:

- request count for `/predict`.
- p50 or p99 prediction latency.
- active model version gauge.

Metrics emission should be best-effort. If Pushgateway is unavailable, log a
warning and continue the pipeline.
