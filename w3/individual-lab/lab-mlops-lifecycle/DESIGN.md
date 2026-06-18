# DESIGN.md - MLOps Lifecycle

## 1. Drift Threshold

I use a default drift threshold of `0.15`, meaning retrain starts when more than 15% of monitored feature columns are considered drifted. The baseline no-drift reference is `baseline.csv`, which represents 4320 rows over 30 days; the current drift window is `drifted.csv`, which represents 1008 rows over 7 days. The lab data intentionally shifts latency by about 30%, doubles error rate, and raises traffic by about 40%, so a threshold below the measured drift score is expected to trigger retraining. If the threshold is too low, for example `0.05`, normal intra-day traffic variation could cause false retrains; if it is too high, the model may keep serving after the new latency and error-rate baseline has become production reality.

## 2. Drift Type

`drift_detector.py` detects data drift with Evidently `DataDriftPreset`, which means it checks whether the input feature distribution `P(X)` changed for `latency_p99`, `error_rate`, and `rps`. This is appropriate for the payment anomaly problem because the original model learned what normal latency, error rate, and traffic looked like before the campaign and third-party integrations. The lab also includes a concept-drift trap through `anomaly_label`, where the relationship between features and labels can change. `DataDriftPreset` does not directly detect concept drift, so combined mode adds a labeled precision/recall check and prints both `Drift score` and `Perf precision`.

## 3. Retrain Trigger Configuration

The trigger is semi-automatic: drift detection and v2 training are automatic, but promotion to production requires a human approval prompt. The approver is the ML engineer or platform on-call engineer who owns the payment anomaly detector. In this lab the prompt waits in the terminal and any response except `y` or `Y` rejects promotion; in production I would use a 24-hour timeout and archive stale staging models. I do not run a fixed weekly retrain because this lab has a strong drift signal, so retrain-on-drift is more explainable and avoids unnecessary version churn.

## 4. Versioning And Rollback

The pipeline uses MLflow Registry aliases rather than hard-coded version numbers in serving code. `serve.py` always loads `models:/anomaly-detector@production`, while `retrain.py` assigns the new candidate to `staging` and moves the `production` alias only after approval. Rollback restores the previous production version by moving `production` back to v1, assigning the degraded v2 to `archived`, and calling `POST /reload` on the FastAPI service. The ML engineer on call has authority to trigger rollback, and the auto-rollback path records the decision in `outputs/audit_log.jsonl`.

## 5. Combined Drift Mode

Combined mode is necessary because data drift and performance degradation catch different failures. A data-only check can detect the 30% latency increase and 40% traffic increase, but it cannot know whether the model's anomaly labels are still correct. A performance check with labeled data can catch precision dropping below the configured `0.70` threshold even if feature distributions look normal. In the lab command, `--check-mode combined --labeled-current data-pack/data/drifted.csv --model-uri models:/anomaly-detector@production` triggers when either the Evidently drift score exceeds `0.15` or precision is below `0.70`.

## 6. Retrain Data Selection

`retrain.py` trains v2 on a sliding window made from `baseline.csv + drifted.csv`, for 4320 + 1008 = 5328 rows. This keeps both the old operating regime and the new campaign/integration regime visible to IsolationForest. The alternative, training only on the 1008-row drift window, is simpler but can overfit to the new distribution and perform worse on `holdout.csv`, which contains old-pattern traffic. The holdout validation line compares v2 precision and recall, and the script also attempts to print v1 precision on the same holdout for context.

## 7. Auto-Rollback Policy

After promotion, `retrain.py --post-deploy-eval data-pack/data/post_deploy_eval.csv` runs up to 24 simulated monitoring cycles. If v2 precision is below `0.65`, the pipeline automatically demotes v2 to `@archived`, restores v1 to `@production`, reloads the service, and writes an `auto_rollback_v2_to_v1` audit event. The `0.65` threshold is intentionally below the original 91% validation precision, so rollback is reserved for severe degradation rather than small sample noise. The audit event includes `demoted_version`, `restored_version`, `trigger_precision`, and `cycle`.
