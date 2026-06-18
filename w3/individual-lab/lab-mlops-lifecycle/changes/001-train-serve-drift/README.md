# 001 - Train, Register, Serve, And Detect Drift

This change introduces the minimum working MLOps lifecycle components.

Scope:

- `pipeline.py` for training and MLflow registration.
- `serve.py` for FastAPI model serving.
- `drift_detector.py` for data-drift detection.
- Basic MLflow metrics and drift report artifacts.
- Minimum `DESIGN.md`, `SUBMIT.md`, and root `README.md` drafts.

Out of scope:

- Full retrain orchestration.
- Approval gate and production promotion.
- Holdout validation.
- Post-deploy auto-rollback.
- Excellent-level stress scenarios.
