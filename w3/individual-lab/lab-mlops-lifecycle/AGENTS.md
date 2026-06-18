# AGENTS.md

Guidance for AI agents working on the Week 3 individual lab:
MLOps Lifecycle.

## Environment

Project type: local Python MLOps pipeline for anomaly detection lifecycle
management. The lab uses MLflow, PostgreSQL, Prometheus, Pushgateway, Grafana,
FastAPI, Evidently, and scikit-learn.

Lab root:

```powershell
cd w3/individual-lab/lab-mlops-lifecycle
```

The provided lab pack runs its infrastructure through Docker Compose and local
Python through `uv`.

```powershell
cd data-pack
bash scripts/start_stack.sh
```

Stop the stack:

```powershell
cd data-pack
bash scripts/stop_stack.sh
```

Required Python packages for the learner implementation:

```powershell
uv pip install "mlflow==2.13.2" "evidently==0.4.40" scikit-learn pandas numpy fastapi uvicorn prometheus_client requests
```

If the environment requires Python 3.11, use `uv run --python 3.11
--no-project --with ...` as described in `data-pack/README.md`.

## Read First

Before implementing:

1. `data-pack/HANDOUT.md`
2. `data-pack/README.md`
3. `specs/README.md`
4. `specs/system-context.md`
5. `specs/runtime-contracts.md`
6. `specs/data-observability.md`
7. Relevant change folder under `changes/`
8. Existing learner-owned files at the lab root, if present

Do not infer requirements from the sample solution alone. The handout and specs
are the source of truth. Use `data-pack/sample-solution/` only as a reference
after the implementation direction is clear.

## Submission Boundary

In the handout, `your-name/` means the learner submission directory. In this
repo, treat `w3/individual-lab/lab-mlops-lifecycle/` as that working submission
root unless the user explicitly creates a separate named folder.

Expected learner-owned files at the submission root:

```text
pipeline.py
serve.py
drift_detector.py
retrain.py
DESIGN.md
SUBMIT.md
README.md
```

`data-pack/` is provided lab material. Avoid editing it unless the user asks for
lab-pack maintenance. Learner code should read from it, start its stack, or use
its datasets and configs.

## Project Boundaries

- Preserve the contracts in `data-pack/HANDOUT.md`.
- Keep stable architecture and data knowledge in `specs/`.
- Keep feature-specific implementation plans in `changes/`.
- Do not require cloud services. The lab must run locally.
- Do not require Grafana for grading. Grafana is for debugging and visibility.
- Do not hard-code model registry state as `latest`.
- Do not promote a retrained model to production without an approval gate.
- Do not use a drift threshold without documenting the measured rationale.
- Do not overwrite model files directly; use MLflow Registry aliases.

## Domain Rules

- The lifecycle sequence is Train, Register, Serve, Detect Drift, Retrain,
  Stage, Approve, Promote, Reload, Monitor, and Roll Back when needed.
- The registered model name is `anomaly-detector`.
- Use MLflow aliases for runtime routing:
  - `production` for the active model served by FastAPI.
  - `staging` for the candidate retrained model.
  - `archived` for a demoted model after rollback.
- `serve.py` should load `models:/anomaly-detector@production` at startup and
  reload from the same alias after promotion or rollback.
- Data drift is detected from feature distribution changes.
- Concept or performance drift requires labeled evaluation or model performance
  checks; do not claim `DataDriftPreset` detects it directly.
- Retrain data should preserve both old and new regimes unless the user
  explicitly asks to test overfitting behavior.
- Rollback must restore the previous production alias and reload the service.
- Write audit events for promotion and rollback decisions.

## Naming Rules

Follow Python PEP 8 naming conventions:

- Modules and files: `snake_case.py`
- Packages/directories: `snake_case`
- Functions, methods, and variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Classes and dataclasses: `PascalCase`
- Private helpers: prefix with `_`

Use domain-specific names:

- `reference_df` for baseline or reference production data.
- `current_df` for the current production or drift window.
- `holdout_df` for labeled old-pattern validation data.
- `post_deploy_df` for labeled post-promotion monitoring data.
- `drift_result` for drift score, flag, and report path.
- `model_version` for the MLflow registered model version.
- `production_version` for the active alias target.
- `staging_version` for the retrain candidate.
- `audit_event` for one structured audit log entry.

Avoid vague names such as `data`, `result`, `item`, `obj`, and `tmp` unless the
scope is tiny and obvious.

## Clean Code Rules

- Separate training, registry operations, serving, drift detection, retrain
  orchestration, monitoring, and audit logging.
- Use `pathlib.Path` for file paths.
- Use explicit request timeouts for calls to `serve.py`.
- Prefer typed dataclasses for drift results, evaluation results, and lifecycle
  decisions.
- Keep MLflow setup in small helpers so scripts share the same model name and
  tracking URI behavior.
- Use structured JSONL for `outputs/audit_log.jsonl`.
- Avoid broad `except Exception` unless logging context and returning a safe
  refusal.
- Do not silently skip failed MLflow registration, alias swap, reload, or
  rollback operations.
- Keep command-line defaults aligned with the provided datasets.

## Checks

Minimum local checks before submission:

```powershell
uv run python pipeline.py --data data-pack/data/baseline.csv
uv run python serve.py
uv run python drift_detector.py --reference data-pack/data/baseline.csv --current data-pack/data/drifted.csv --check-mode combined --model-uri models:/anomaly-detector@production --labeled-current data-pack/data/drifted.csv
uv run python retrain.py --reference data-pack/data/baseline.csv --current data-pack/data/drifted.csv --holdout data-pack/data/holdout.csv --post-deploy-eval data-pack/data/post_deploy_eval.csv
```

Also verify:

- `GET http://localhost:5000/health` for MLflow.
- `GET http://localhost:8000/health/active-version` for the model server.
- `outputs/drift_reports/` contains an Evidently HTML report.
- `outputs/audit_log.jsonl` contains promotion or rollback events when those
  paths run.

If a dependency or service is unavailable, report the exact skipped check and
the blocking condition.
