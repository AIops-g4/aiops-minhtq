# System Context

## Objective

Build a local MLOps lifecycle for a fintech payment-gateway anomaly detector.
The pipeline must train an IsolationForest model, register it in MLflow, serve
it through FastAPI, detect production drift, retrain safely, promote through a
blue-green alias swap, and roll back when post-deploy quality degrades.

The deliverable should feel like something an MLOps engineer can hand to an
on-call team: observable, versioned, auditable, and recoverable.

## Scenario

The original production model was trained two months ago. It achieved about
91% precision and 88% recall on validation data, but the on-call team now sees
missed incidents and more false positives.

The identified root cause is model decay:

- Traffic increased about 35% after a campaign.
- Latency baseline rose after adding third-party integrations.
- Error-rate patterns changed after a payment processor rollout.

The CTO requires both drift monitoring and a retrain pipeline. A retrain-only
solution or a monitoring-only solution is incomplete.

## Runtime Stack

The provided stack in `data-pack/configs/docker-compose.yml` contains:

- MLflow Tracking Server and Registry on `localhost:5000`.
- PostgreSQL backend store on `localhost:5432`.
- Prometheus on `localhost:9090`.
- Pushgateway on `localhost:9091`.
- Grafana on `localhost:3000`.

Learner-owned scripts run directly on the host through `uv`:

- `pipeline.py`
- `serve.py`
- `drift_detector.py`
- `retrain.py`

## Lifecycle Flow

```text
baseline.csv
-> pipeline.py trains IsolationForest
-> MLflow logs run and registers anomaly-detector v1
-> production alias points to v1
-> serve.py loads models:/anomaly-detector@production
-> drift_detector.py compares baseline and current window
-> retrain.py trains v2 when drift or performance degradation is detected
-> staging alias points to v2
-> human approval gate
-> production alias moves from v1 to v2
-> serve.py reloads production alias
-> post-deploy monitor checks v2
-> rollback restores v1 when v2 underperforms
```

## Submission Root

The handout calls the learner submission directory `your-name/`. In this repo,
treat `w3/individual-lab/lab-mlops-lifecycle/` as the submission root unless
the user explicitly asks for a separate named directory.

Required learner-owned files:

```text
pipeline.py
serve.py
drift_detector.py
retrain.py
DESIGN.md
SUBMIT.md
README.md
```

`data-pack/` is provided input material and should remain stable during learner
implementation.

## Non-Negotiable Constraints

- Train and register through MLflow, not an untracked local pickle only.
- Register under model name `anomaly-detector`.
- Route production serving through the MLflow alias `production`.
- Provide `/predict`, `/health/active-version`, and `/reload`.
- Save drift reports under `outputs/drift_reports/`.
- Justify the drift threshold with measured numbers.
- Use an approval gate before promotion to production.
- Preserve rollback by keeping immutable MLflow versions and moving aliases.
- Do not depend on cloud services or GPU hardware.
- Do not make Grafana a grading dependency.

## Default Implementation Direction

Use a deterministic, local implementation:

- `IsolationForest` from scikit-learn.
- MLflow pyfunc or sklearn model logging.
- Evidently `DataDriftPreset` for data drift.
- Labeled evaluation for performance or concept-drift proxy checks.
- Terminal approval prompt for promotion.
- JSONL audit log for lifecycle decisions.

Advanced orchestration frameworks are unnecessary unless the user explicitly
requests them.
