# 002 - Retrain, Approval Gate, And Blue-Green Rollout

This change completes the required lifecycle loop after drift is detected.

Scope:

- `retrain.py` orchestrator.
- Sliding-window retrain data selection.
- v2 registration under `staging`.
- Human approval gate.
- Alias promotion from `staging` to `production`.
- FastAPI reload after promotion.
- Holdout validation for acceptance criterion 5.

Out of scope:

- Post-deploy 24-cycle auto-rollback.
- Combined data and performance drift stress mode.
- Grafana dashboard customization.
