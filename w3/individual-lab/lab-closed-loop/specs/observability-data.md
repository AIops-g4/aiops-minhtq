# Observability And Data

## Service And Container Names

Prometheus, Alertmanager, and application metrics use short service labels:

- `frontend`
- `api-gateway`
- `payment-svc`
- `inventory-svc`
- `checkout-svc`

Docker containers use prefixed names:

- `ronki-frontend`
- `ronki-api-gateway`
- `ronki-payment-svc`
- `ronki-inventory-svc`
- `ronki-checkout-svc`

Runbooks should accept short service labels and derive container names
internally.

## Ports

- `frontend`: `localhost:8080`
- `api-gateway`: `localhost:8081`
- `payment-svc`: `localhost:8082`
- `inventory-svc`: `localhost:8083`
- `checkout-svc`: `localhost:8084`
- Prometheus: `localhost:9090`
- Alertmanager: `localhost:9093`
- Grafana: `localhost:3000`
- Loki: `localhost:3100`
- Orchestrator metrics endpoint: `localhost:9100`

## Alert Rules

Defined in `data-pack/configs/alert_rules.yml`:

- `HighLatency`: p99 request latency greater than 500 ms for 30 seconds.
- `HighErrorRate`: HTTP error rate greater than 10 percent for 30 seconds.
- `InstanceDown`: Prometheus `up == 0` for 30 seconds.

## Baseline And Verify Thresholds

Baseline source:

```text
data-pack/data/baseline.json
```

Key thresholds:

- `latency_p99_max_ms`: 500
- `error_rate_max_pct`: 10.0
- `up_required`: 1
- `verify_timeout_seconds`: 60
- `verify_poll_interval_seconds`: 10
- `verify_min_samples`: 3

Prometheus queries are also defined in `baseline.json` and use `{service}` as a
placeholder.

## Acceptance Scenarios

Required scenarios:

1. Latency on `payment-svc` must lead to `ACTION_SUCCESS`.
2. Killed or forced-unhealthy `checkout-svc` must lead to rollback.
3. Three consecutive failures must lead to `CIRCUIT_BREAKER_HALT`.

Excellent-level stress scenarios:

4. Multi-step deploy failure must rollback completed steps in reverse order.
5. Concurrent alerts for different services must proceed in parallel; duplicate
   same-service alerts must log `SERVICE_LOCK_BUSY`.
6. Invalid or hallucinated runbook decisions must log
   `DECISION_VALIDATION_FAILED` and spawn no subprocess.

Detailed expected event sequences are in `data-pack/data/expected.json`.

## Dashboard Notes

Grafana dashboard `AIOps Closed-Loop` expects orchestrator metrics and audit log
events. The dashboard is not a grading criterion, but the learner should expose
metrics if implementing the excellent path.

Useful optional metrics:

- `closed_loop_actions_total{service,runbook,outcome}`
- `closed_loop_circuit_breaker_state{service}`
- `closed_loop_blast_radius_remaining`
- `closed_loop_mutex_locked{service}`
- `closed_loop_verify_status{service}`
