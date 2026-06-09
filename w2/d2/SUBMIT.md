# W2/D2 RCA Submission

## EOD checkpoint

1. The top-1 confidence in the largest cluster (`c-001-000`) is `0.89`. If I had to set a threshold for auto-rollback without SRE confirmation, I would choose `0.90`. The reason is that the current output is very close to the threshold and points in the right direction for payment, but production rollback still needs additional guards such as a recent deploy, error budget burn, and a sustained pool-full metric. With graph + retrieval alone, `0.89` is enough to page the payments team and recommend rollback, but not enough to automatically rollback every time.

2. The classifier variant I chose is `A rule-based / retrieval-only`. The notebook takes the top-3 historical incidents by service overlap, severity, and root cause presence in the cluster, then uses the nearest incident matching the top-1 root cause to derive class/actions. In the actual run, the main cluster produced `payment-svc` with class `connection_pool_exhaustion` and similar incidents `INC-2025-11-08, INC-2026-05-10, INC-2025-09-05`. Compared with free/paid LLMs, this approach is less flexible in reasoning, but it is deterministic, needs no API key, has no timeout risk, and is easy to debug in the lab.

3. This pipeline is closest to Dynatrace Davis because it relies heavily on the service graph/topology and then combines temporal signal with incident history to rank the culprit. For GeekShop, an e-commerce domain with high alert volume and a relatively stable service map, this is a reasonable choice for first-pass triage. However, topology should not be treated as absolute truth: cases such as async Kafka, shared DBs, or independent batch retrains like `recommender-svc` need additional metric/trace signals or human review to avoid incorrect auto-remediation.

## Artifacts

- `assignment.ipynb`
- `results/rca_output.json`
- `FINDINGS.md`
- `SUBMIT.md`
