# SUBMIT.md - Reflection

## 1. What drift threshold did you choose and why?

I chose `0.15` as the default drift threshold in `drift_detector.py` and `retrain.py`. The reference data has 4320 baseline rows, while `drifted.csv` has 1008 current rows with latency up about 30%, error rate roughly doubled, and traffic up about 40%. That makes `0.15` low enough to catch the lab's real drift but high enough to avoid retraining on small daily noise. The threshold is passed as a CLI option, so it can be tuned after measuring baseline split drift and production drift scores.

## 2. What happens if model v2 performs worse than v1?

Before promotion, `retrain.py` evaluates v2 on `holdout.csv` and prints `Holdout validation — v2 precision: ... recall: ...`. It also attempts to evaluate the current production model on the same holdout, so the reviewer can compare v1 and v2 before approving promotion. If v2 is already in production and `--post-deploy-eval` shows precision below `0.65`, auto-rollback restores the previous production version and archives v2. The rollback event is written to `outputs/audit_log.jsonl` as `auto_rollback_v2_to_v1`.

## 3. What is the difference between data drift and concept drift?

Data drift means the input feature distribution changes, for example latency moving from about 120 ms toward a higher post-integration baseline. Concept drift means the relationship between input features and the true label changes, so the same latency and error-rate pattern may no longer mean the same anomaly state. Evidently `DataDriftPreset` detects data drift from `latency_p99`, `error_rate`, and `rps`; it does not directly detect concept drift. That is why `drift_detector.py --check-mode combined` adds a labeled precision/recall check.

## 4. Why is blue-green swap better than replacing the model file directly?

Replacing a model file directly creates a weak rollback story and can race with active requests. In this lab, MLflow versions are immutable and serving uses the `production` alias, so promotion is a registry alias move followed by `POST /reload`. If v2 is bad, rollback is another alias move back to v1 plus another reload, without changing code or deleting artifacts. `/health/active-version` makes the active version observable before and after the swap.

## 5. If approval were fully automated, what metric and threshold would you use?

I would automate approval only when v2 passes holdout validation and a short post-deploy shadow evaluation. The primary metric would be precision, with v2 required to be at least v1 precision on `holdout.csv` and at least `0.70` on labeled current data. I would also require recall not to drop by more than five percentage points from v1 on the same evaluation window. If any condition fails, the model should stay in `staging` and alert the ML engineer rather than promoting automatically.
