# 001 - Train, Register, Serve, And Detect Drift Spec

## Goal

Build the baseline lifecycle path: train model v1, register it as production,
serve predictions, and detect data drift between the baseline and current data
window.

## Inputs

Datasets:

- `data-pack/data/baseline.csv`
- `data-pack/data/drifted.csv`

Runtime services:

- MLflow on `http://localhost:5000`
- Prometheus and Pushgateway are optional for this change.

## Training Behavior

`pipeline.py` must:

1. Load the requested CSV.
2. Select feature columns `latency_p99`, `error_rate`, and `rps`.
3. Train an `IsolationForest`.
4. Log params, metrics, and the model artifact to MLflow.
5. Register the artifact under `anomaly-detector`.
6. Set alias `production` for the registered version.

The command below should create the first production model:

```powershell
uv run python pipeline.py --data data-pack/data/baseline.csv
```

## Serving Behavior

`serve.py` must:

1. Load `models:/anomaly-detector@production` on startup.
2. Expose `POST /predict`.
3. Expose `GET /health/active-version`.
4. Expose `POST /reload`.
5. Expose `GET /metrics` when `prometheus_client` is installed.

The active version endpoint must show which MLflow model version is loaded.
This is required later to verify blue-green swaps.

## Drift Detection Behavior

`drift_detector.py` must:

1. Load reference and current CSVs.
2. Compare feature distributions with Evidently `DataDriftPreset`.
3. Compute a drift score and boolean flag.
4. Save an HTML report under `outputs/drift_reports/`.
5. Print `Drift score`.
6. Log drift score to MLflow.

Default command:

```powershell
uv run python drift_detector.py --reference data-pack/data/baseline.csv --current data-pack/data/drifted.csv
```

## Acceptance Criteria

- MLflow contains a run with IsolationForest params and train metrics.
- MLflow Registry contains `anomaly-detector` with alias `production`.
- `serve.py` returns a prediction with `prediction`, `score`, and `version`.
- `/health/active-version` returns the currently loaded version.
- `drift_detector.py` saves an HTML report.
- `drift_detector.py` flags `drifted.csv` as drift when using the documented
  threshold.
- `DESIGN.md` records the initial threshold rationale with measured numbers.
