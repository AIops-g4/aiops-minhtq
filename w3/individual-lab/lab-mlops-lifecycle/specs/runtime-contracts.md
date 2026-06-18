# Runtime Contracts

## Stack Commands

Start infrastructure from the provided lab pack:

```powershell
cd data-pack
bash scripts/start_stack.sh
```

Stop infrastructure:

```powershell
cd data-pack
bash scripts/stop_stack.sh
```

Health checks:

```powershell
curl -s http://localhost:5000/health
curl -s http://localhost:9090/-/healthy
curl -s http://localhost:9091/-/healthy
curl -s http://localhost:3000/api/health
```

## Model Registry Contract

Model name:

```text
anomaly-detector
```

Required aliases:

- `production`: model version served by FastAPI.
- `staging`: retrained candidate waiting for approval.
- `archived`: demoted model after rollback.

Serving code should load:

```text
models:/anomaly-detector@production
```

Do not hard-code registered model version numbers in `serve.py`.

## `pipeline.py` Contract

Primary command:

```powershell
uv run python pipeline.py --data data-pack/data/baseline.csv
```

Expected behavior:

- Read CSV with feature columns `latency_p99`, `error_rate`, and `rps`.
- Train scikit-learn `IsolationForest`.
- Log parameters to MLflow:
  - `contamination`
  - `n_estimators`
  - `random_state`
- Log metrics to MLflow:
  - `train_anomaly_rate`
  - `feature_count`
- Log model artifact through `mlflow.sklearn.log_model`.
- Register the model as `anomaly-detector`.
- Set alias `production` for the first production version, or `staging` when
  invoked by retrain flow.

Recommended extra options:

```powershell
uv run python pipeline.py --data data-pack/data/drifted.csv --alias staging
```

## `serve.py` Contract

Primary command:

```powershell
uv run python serve.py
```

Required endpoints:

```text
POST /predict
GET  /health/active-version
POST /reload
GET  /metrics
```

`POST /predict` accepts:

```json
{"features": [120.0, 0.8, 450.0]}
```

It returns:

```json
{"prediction": 1, "score": 0.1234, "version": "1"}
```

`GET /health/active-version` returns the loaded model identity. It must be good
enough to verify an alias swap before and after reload.

`POST /reload` reloads `models:/anomaly-detector@production` without restarting
the process.

## `drift_detector.py` Contract

Primary command:

```powershell
uv run python drift_detector.py --reference data-pack/data/baseline.csv --current data-pack/data/drifted.csv
```

Combined-mode command for stress acceptance:

```powershell
uv run python drift_detector.py --reference data-pack/data/baseline.csv --current data-pack/data/drifted.csv --check-mode combined --model-uri models:/anomaly-detector@production --labeled-current data-pack/data/drifted.csv
```

Required behavior:

- Compare reference and current feature distributions.
- Compute a drift score.
- Return or print whether drift exceeds the configured threshold.
- Save an Evidently HTML report under `outputs/drift_reports/`.
- Log drift score to MLflow.
- Push drift metrics to Pushgateway when available, without crashing when it is
  unavailable.

Check modes:

- `data`: feature-distribution drift only.
- `performance`: labeled model performance check only.
- `combined`: run both checks and trigger if either one fails.

The output for combined mode must include both `Drift score` and
`Perf precision`.

## `retrain.py` Contract

Primary command:

```powershell
uv run python retrain.py --reference data-pack/data/baseline.csv --current data-pack/data/drifted.csv --holdout data-pack/data/holdout.csv
```

End-to-end stress command:

```powershell
uv run python retrain.py --reference data-pack/data/baseline.csv --current data-pack/data/drifted.csv --holdout data-pack/data/holdout.csv --post-deploy-eval data-pack/data/post_deploy_eval.csv
```

Required behavior:

1. Run drift or combined drift detection.
2. If no drift or degradation is detected, stop safely and log the decision.
3. If drift is detected, train v2 using a sliding-window strategy.
4. Register v2 and assign alias `staging`.
5. Print the approval prompt:

   ```text
   Drift detected. Model v2 registered as staging. Promote to production? [y/N]
   ```

6. If approved, move `production` to v2 and reload `serve.py`.
7. Monitor post-deploy quality when `--post-deploy-eval` is provided.
8. Roll back to v1 if v2 precision falls below the rollback threshold.

Required holdout output:

```text
Holdout validation — v2 precision: X.XXXX  recall: X.XXXX
```

Required rollback output when triggered:

```text
Rollback complete. v1 restored to @production. v2 → @archived
```

## Audit Log Contract

Write one JSON object per line to:

```text
outputs/audit_log.jsonl
```

Important event names:

- `drift_check_started`
- `drift_detected`
- `no_drift_detected`
- `retrain_started`
- `model_registered_staging`
- `approval_requested`
- `promotion_approved`
- `promotion_rejected`
- `production_reloaded`
- `post_deploy_monitor_cycle`
- `auto_rollback_v2_to_v1`

The `auto_rollback_v2_to_v1` event must include:

- `demoted_version`
- `restored_version`
- `trigger_precision`
- `cycle`

## Documentation Contract

`DESIGN.md` must answer the four original sub-checkpoints and the three stress
scenario design points with concrete numbers from local runs when available.

`SUBMIT.md` must answer the five reflection questions with references to code,
thresholds, versions, and observed outputs.
