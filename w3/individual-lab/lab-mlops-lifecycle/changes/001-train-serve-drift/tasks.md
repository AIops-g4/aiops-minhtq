# 001 - Train, Register, Serve, And Detect Drift Tasks

## Implementation

- [ ] Add shared constants for model name, feature columns, and default paths.
- [ ] Add `pipeline.py` CLI with `--data`, model hyperparameters, and alias
      selection.
- [ ] Train `IsolationForest` on `latency_p99`, `error_rate`, and `rps`.
- [ ] Log MLflow params: `contamination`, `n_estimators`, `random_state`.
- [ ] Log MLflow metrics: `train_anomaly_rate`, `feature_count`.
- [ ] Register model artifact as `anomaly-detector`.
- [ ] Set alias `production` for v1.
- [ ] Add `serve.py` FastAPI app.
- [ ] Implement `/predict`, `/health/active-version`, `/reload`, and
      `/metrics`.
- [ ] Add `drift_detector.py` with Evidently data-drift report generation.
- [ ] Save reports to `outputs/drift_reports/`.
- [ ] Log drift score to MLflow.
- [ ] Add initial `README.md`, `DESIGN.md`, and `SUBMIT.md` skeletons.

## Validation

- [ ] Start the lab stack from `data-pack`.
- [ ] Confirm MLflow health on `localhost:5000`.
- [ ] Run `uv run python pipeline.py --data data-pack/data/baseline.csv`.
- [ ] Confirm `anomaly-detector@production` exists in MLflow.
- [ ] Run `uv run python serve.py`.
- [ ] Call `GET /health/active-version`.
- [ ] Call `POST /predict` with one feature vector.
- [ ] Run `drift_detector.py` against baseline and drifted data.
- [ ] Confirm terminal output contains `Drift score`.
- [ ] Confirm an HTML drift report exists under `outputs/drift_reports/`.

## Documentation

- [ ] In `DESIGN.md`, explain the chosen threshold and measured drift score.
- [ ] In `SUBMIT.md`, answer the threshold reflection question using real
      output.
- [ ] In root `README.md`, document the minimum commands to run train, serve,
      and drift detection.
