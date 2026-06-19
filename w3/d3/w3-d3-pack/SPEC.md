# AIOps Mini-Platform Spec - minhtq

## 1. Platform overview
The platform monitors a small ecommerce-style service stack with frontend, API, database, gateway, payment, inventory, auth, DNS, and observability components. Its users are SREs and on-call engineers who need fast detection, event correlation, and root-cause ranking during incidents. The scope is detection, correlation, RCA evidence, and operator-facing runbook guidance; it does not replace human incident command.

## 2. SLO definition (from W3-D1)
The W3-D1 SLO spec defines three service SLOs:

| Service | SLI | SLO | Error budget |
|---|---|---:|---:|
| frontend | RUM page-load events with dom_ready_ms < 3000 and no JS or network error / all RUM page-load events | 98.0% over 30 days | 103,680 failed events/month, about 864 minutes |
| api | HTTP requests that are not 5xx or 429 / all HTTP requests | 99.9% over 30 days | 20,738 failed events/month, about 43 minutes |
| db | Successful DB queries with duration_ms < 100 / all sampled DB queries | 99.4% over 30 days | 10,358 failed events/month, about 259 minutes |

The source file is `../../d1/slo_spec.yaml`.

## 3. Detection + Correlation + RCA stack (from W1+W2)
The detector uses service-level availability, latency, error-rate, and lifecycle signals to emit alerts with service, metric, severity, and fire timestamp. The correlator groups alerts within a short incident window and prefers clusters that share topology edges or a common change window. RCA uses topology-aware ranking with change-event correlation, as recorded in ADR-001, so simultaneous symptoms can be traced to control-plane or maintenance-scope causes instead of only the loudest downstream service.

## 4. Reliability validation (from W3-D2)
W3-D2 chaos validation ran 10 experiments. The pipeline detected 9/10, RCA was correct for 8/9 detected incidents, false alarms were 0, precision was 1.00, recall was 0.90, and MTTD p50/p95 was 3 seconds.

Top 3 gaps:
1. `log_collector_disk_fill` was missed because the detector lacks meta-monitoring for log ingestion lag, write failures, queue lag, and disk usage.
2. `dns_lookup_latency` was detected but RCA selected `api-gateway`, showing topology/evidence ranking weakness around DNS dependencies.
3. Whole-run probe pass-rate mixed fault and recovery windows, so reports need per-experiment pass-rate and a post-rollback recovery gate.

## 5. Operational pattern (from W3-D3)
The reproduced outage is AWS S3 us-east-1 from 2017-02-28. The key learning is that destructive operational commands need blast-radius controls, dry-run previews, and correlation with audit/change events. ADR-001 records the design decision to use topology-aware RCA with change-event correlation so the platform can connect billing-control, s3-index, and s3-placement symptoms to the maintenance-command scope.

## 6. Cost model (from W3-D3)
Current stack input:

```text
num_services=20
incidents_per_month=2
avg_incident_duration_hours=1
downtime_cost_per_hour=10000
expected_mttr_reduction_pct=0.4
aiops_monthly_cost=15000
```

Output:

```text
monthly_value=8000.0
monthly_cost=15000.0
roi=0.5333333333333333
payback_months=inf
verdict=not_worth_it
```

Break-even point: at 40% MTTR reduction, 1 hour per incident, and USD 10,000/hour downtime cost, each incident is worth USD 4,000 in avoided downtime. A USD 15,000/month platform cost needs 3.75 avoided-equivalent incidents per month, rounded up to about 4 incidents/month.

## 7. Open risks
1. **High:** Change-event ingestion can be incomplete. Mitigation: require audit logs and deploy events as first-class RCA inputs.
2. **High:** Topology data can become stale. Mitigation: generate dependency edges from service config and traces, then validate weekly.
3. **Medium:** Observability-stack failures can hide incidents. Mitigation: add meta-monitoring for log ingestion, queue lag, and collector disk usage.
4. **Medium:** RCA may over-rank user-facing symptoms. Mitigation: add causal-lag evidence and dependency-specific metrics such as DNS lookup latency.
5. **Low:** Cost value is sensitive to downtime-cost assumptions. Mitigation: revisit cost inputs quarterly with finance and support data.
