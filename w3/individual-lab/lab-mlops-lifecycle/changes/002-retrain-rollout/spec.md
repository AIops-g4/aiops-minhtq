# 002 - Retrain, Approval Gate, And Blue-Green Rollout Spec

## Goal

When drift is detected, train a new candidate model, register it as staging,
validate it against holdout data, require human approval, then promote it to
production through an MLflow alias swap and FastAPI reload.

## Inputs

Datasets:

- `data-pack/data/baseline.csv`
- `data-pack/data/drifted.csv`
- `data-pack/data/holdout.csv`

Runtime services:

- MLflow on `http://localhost:5000`
- `serve.py` on `http://localhost:8000`

## Retrain Trigger Behavior

`retrain.py` must call drift detection before training a new candidate.

If drift is not detected:

- Do not train a new model.
- Log a no-op decision.
- Exit successfully.

If drift is detected:

- Build a training window that includes both baseline and drifted data.
- Train v2.
- Register v2 under `anomaly-detector`.
- Set alias `staging` to v2.

## Sliding-Window Strategy

The default training set should concatenate:

```text
baseline.csv + drifted.csv
```

This prevents v2 from overfitting only to the seven-day drift window and losing
performance on old-pattern traffic.

`DESIGN.md` must compare this strategy against at least one alternative, such
as drift-window-only training.

## Holdout Validation

Evaluate both v1 and v2 on `holdout.csv` with the same prediction-to-label
mapping.

Required terminal line:

```text
Holdout validation — v2 precision: X.XXXX  recall: X.XXXX
```

Acceptance criterion 5 requires v2 precision to be at least v1 precision on the
same holdout.

## Approval Gate

After registering v2 as staging, print:

```text
Drift detected. Model v2 registered as staging. Promote to production? [y/N]
```

Only `y` or `Y` should approve promotion. Any other answer should leave
production unchanged.

## Promotion Behavior

When approved:

1. Capture the previous production version as rollback target.
2. Move `production` alias to the staging version.
3. Call `POST http://localhost:8000/reload` with a request timeout.
4. Confirm `/health/active-version` shows the promoted version.
5. Append audit events to `outputs/audit_log.jsonl`.

Promotion must not require modifying `serve.py` code or restarting the server.

## Acceptance Criteria

- Drift detection triggers retrain for `drifted.csv`.
- v2 is registered and assigned alias `staging`.
- Holdout validation line is printed.
- Promotion requires explicit approval.
- After approval, `production` points to v2.
- `serve.py` reloads and reports v2 as active.
- If approval is rejected, production remains v1.
- `DESIGN.md` documents approval authority, timeout policy, and rollback path.
