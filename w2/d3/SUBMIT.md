# W2/D3 Submission

## Artifacts

- `serve.py`
- `DESIGN.md`
- `SUBMIT.md`

## EOD Checkpoint

1. Latency of the endpoint was measured with uvicorn from `w2/d3` using `python -m uvicorn serve:app --host 127.0.0.1 --port 8012 --workers 1`. I sent the 20-alert dataset from `w2/d1/data/alerts_sample.jsonl` to `POST /incident` 20 times sequentially and read `X-Response-Time-Ms`. The warm benchmark was p50 `3.52 ms`, p99 `7.40 ms`, min `3.26 ms`, and max `7.40 ms`. The first cold request after startup was `296.13 ms`. Validation and serialization are small fixed costs for this dataset. Correlation and RCA scale with alert count and number of services in the primary cluster. There is no LLM phase in the default run, so no external network latency dominates.

2. `AIOPS_USE_LLM` defaults to `false`, so provider outage does not block the endpoint. The service returns deterministic graph plus retrieval output with method `graph+retrieval`. If the flag is turned on, this version still does not call a real provider; it marks the method as `graph+retrieval-llm-flag-on-no-provider`. In a real deployment, the first bottleneck under 4 concurrent requests would likely be the outbound LLM call and its timeout/retry behavior. For this lab, the fallback path is the default path: graph correlation, graph/temporal RCA, and history-based actions.

3. `/healthz` checks only that the process is alive and can answer HTTP, returning `{"status":"ok"}`. `/readyz` checks whether the service graph has nodes, incident history has records, and the configured LLM requirement is satisfiable. They are separate because liveness and readiness answer different operational questions. A process can be alive but not ready to serve incidents if graph/history failed to load. With the default `AIOPS_USE_LLM=false`, `/readyz` still passes when an LLM API is down because this implementation does not depend on an external LLM provider.

## Verification

Local uvicorn checks:

- `GET /healthz` returned `200`.
- `GET /readyz` returned `200`.
- `GET /version` returned `200`.
- `POST /incident` with the valid 20-alert sample returned `200`.
- Valid response contained `clusters`, `root_cause`, `recommended_actions`, and `similar_incidents`.
- Empty alert batch returned `400`.
- Malformed alert payload returned `422`.

The valid sample produced root cause `payment-svc`, class `connection_pool_exhaustion`, and recommended actions:

- `Rollback to v3.1`
- `Scale pool 50 -> 100 cushion`
- `Add pool monitor alert > 80%`
