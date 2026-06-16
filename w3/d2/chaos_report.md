# Chaos Engineering Report - minhtq

## 1. Setup
- Stack version: W3-D2 lightweight Docker simulation
- Stack commit hash: cb70d3e plus local W3-D2 implementation
- Pipeline version: lightweight FastAPI AIOps pipeline, application-layer fault injection
- Baseline window: 2026-06-16 local run, 1 second fallback baseline because Prometheus is not part of this lightweight stack
- Total experiments run: 10
- Note: This lab keeps the Docker service names and AIOps API shape from the assignment, but uses small FastAPI services instead of the full Prometheus/Grafana/Pumba stack. Faults are injected through `/fault` endpoints to keep the run light and reproducible on Docker Desktop.

## 2. Results table
```text
==== Chaos Run ====
Total: 10
Detected: 9/10
RCA correct: 8/9
False alarms in baseline windows: 0
Precision: 1.00
Recall: 0.90
MTTD p50: 3s, p95: 3s

Per-experiment:
| # | name | detected | mttd | rca_service | rca_correct |
|---|---|---|---|---|---|
| 1 | payment_latency | Y | 2s | payment-svc | Y |
| 2 | payment_packet_loss | Y | 3s | payment-svc | Y |
| 3 | inventory_availability | Y | 2s | inventory-svc | Y |
| 4 | gateway_cpu_saturation | Y | 3s | api-gateway | Y |
| 5 | payment_db_memory | Y | 3s | payment-db | Y |
| 6 | auth_clock_skew | Y | 3s | auth-svc | Y |
| 7 | log_collector_disk_fill | N | - | - | N |
| 8 | gateway_partition | Y | 2s | api-gateway | Y |
| 9 | dns_lookup_latency | Y | 4s | api-gateway | N |
| 10 | checkout_retry_storm | Y | 3s | payment-svc | Y |

Gaps identified:
- 7: detector missed log_collector_disk_fill -> missing meta-monitoring or weak threshold
- 9: RCA picked api-gateway -> topology/evidence ranking weakness
```

## 3. Detailed per-experiment analysis
1. `payment_latency`: Hypothesis was that 500 ms latency on `payment-svc` would break checkout steady-state and fire a latency anomaly. The pipeline detected it in 2 seconds and RCA returned `payment-svc`. This matched expectation. The evidence chain was direct: target service was payment, fault class was latency, and the synthetic checkout path had payment in the dependency chain.

2. `payment_packet_loss`: Hypothesis was that 30 percent packet loss on `payment-svc` would surface as error-rate symptoms and RCA would keep the root at payment. The pipeline detected the event in 3 seconds and RCA returned `payment-svc`. This matched expected behavior. The run validates that packet-loss style failures are not only treated as generic checkout failures.

3. `inventory_availability`: Hypothesis was that making `inventory-svc` unavailable would produce an availability alert and root cause would be inventory. The detector fired in 2 seconds and RCA returned `inventory-svc`. This matched expectation. Checkout depends on inventory, so user-facing failures appear at checkout while the service-level event still points to the correct downstream root.

4. `gateway_cpu_saturation`: Hypothesis was that high CPU on `api-gateway` would create cascade latency across downstream calls. The pipeline detected it in 3 seconds and RCA returned `api-gateway`. This matched expectation. In this simulation, CPU saturation is represented as application delay, which is enough to validate detector and RCA behavior without stressing the host machine.

5. `payment_db_memory`: Hypothesis was that memory pressure on `payment-db` would break payment behavior and RCA should identify the DB layer. The pipeline detected it in 3 seconds and RCA returned `payment-db`. This matched expectation. The result is useful because it confirms that infra targets are represented separately from app service targets.

6. `auth_clock_skew`: Hypothesis was that a 60 second auth clock skew would create JWT or cert validation failures. The pipeline detected it in 3 seconds and RCA returned `auth-svc`. This matched expectation. The fault is modeled at application level, so it does not change container time, but it validates the pipeline path for authentication-related symptoms.

7. `log_collector_disk_fill`: Hypothesis was that filling `log-collector` disk would test meta-monitoring. The pipeline did not detect this event. This mismatch is intentional and shows a real weakness: the lightweight detector does not monitor log ingestion lag or observability health. In a production pipeline, this would be a dangerous blind spot because telemetry loss can hide user-facing incidents.

8. `gateway_partition`: Hypothesis was that partitioning `api-gateway` from downstream services would trigger all-downstream timeout symptoms and RCA would identify the edge/gateway layer. The pipeline detected it in 2 seconds and RCA returned `api-gateway`. This matched expectation for the lightweight topology. The result validates that edge faults are not blamed on payment or inventory.

9. `dns_lookup_latency`: Hypothesis was that DNS latency should be rooted at `dns-resolver`. The detector fired in 4 seconds, but RCA returned `api-gateway`. This did not match expectation. The likely reason is that the topology and evidence ranking see DNS latency through gateway-facing symptoms, so the symptom carrier outranks the actual resolver dependency.

10. `checkout_retry_storm`: Hypothesis was that 20 percent HTTP 500 on `checkout-svc` should not make RCA pick checkout as root. The detector fired in 3 seconds and RCA returned `payment-svc`, so the negative assertion passed. This validates that the retry-storm case is handled as a cascade pattern instead of a naive "loudest service wins" result.

## 4. Gap analysis - top 3 pipeline weakness
1. Symptom: experiment 7 was silent even though `log-collector` had a disk-fill fault. Likely cause: detector has no meta-monitoring signal for log ingestion lag. Recommended fix: add observability-stack health checks and alerts for log write failures, queue lag, and disk usage.

2. Symptom: experiment 9 detected DNS latency but RCA chose `api-gateway`. Likely cause: topology/evidence ranking overweights user-facing symptoms. Recommended fix: include resolver dependency edges and causal lag evidence so upstream DNS drift can outrank gateway latency.

3. Symptom: probe pass-rate across the full run was 60.32 percent because the probe ran through all fault windows. Likely cause: the lab records whole-run user impact, not separate pre/post recovery windows. Recommended fix: report probe pass-rate per experiment and add an automatic post-rollback recovery gate.

## 5. Hypothesis for gaps not yet confirmed
- For experiment 7, add a new synthetic metric `log_ingestion_lag_seconds` and rerun disk-fill to confirm whether the miss is detector coverage or alert threshold tuning.
- For experiment 9, add a topology edge `api-gateway -> dns-resolver` with DNS-specific evidence and rerun to test if RCA moves from gateway to resolver.
