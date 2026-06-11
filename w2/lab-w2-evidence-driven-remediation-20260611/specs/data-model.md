# Data Model

## Live Incident

Live incidents are loaded from `data-pack/eval/E01.json` through
`data-pack/eval/E08.json`.

Important fields:
- `incident_id`: full incident identifier from the JSON payload.
- `detected_at`: timestamp used to split baseline and post-alert evidence.
- `trigger_alert.service`: service that raised the alert; it is not necessarily
  the root cause.
- `trigger_alert.rule_id`: alert type, such as latency, error rate, DNS, or
  memory leak.
- `topology.nodes` and `topology.edges`: service graph used for dependency and
  cascade reasoning.
- `metrics_window.samples`: time series keyed as `service.metric`.
- `traces`: runtime edge evidence with `from`, `to`, `count`, `error_count`,
  `p50_ms`, and `p99_ms`.
- `logs`: raw service log lines with `ts`, `svc`, `level`, and `msg`.

For `audit.jsonl`, `incident_id` must use the eval file basename such as `E01`,
not the full payload ID.

## Historical Incidents

Historical incidents are loaded from `data-pack/incidents_history.json`.

Important fields:
- `root_cause_class`: useful for analysis, but never a direct action rule.
- `affected_services`: services known to be affected in the historical case.
- `log_signatures`: cleaned historical log templates.
- `trace_signatures`: historical edge-level trace deviations and error rates.
- `metric_signatures`: metric deltas such as `"30 -> 99"`.
- `actions_taken`: strings such as `rollback_service:payment-svc:v3.1`.
- `outcome`: `success`, `partial`, or `failed`; used for action vote weighting.
- `mttr_minutes`: optional supporting signal for action quality.

## Actions

Actions are loaded from `data-pack/actions.yaml`.

Important fields:
- `name`: valid action name.
- `params`: required parameter names for that action.
- `cost_min`, `downtime_min`, `blast_radius_services`,
  `rollback_window_sec`: metadata for decision risk and utility.

`page_oncall` is escalation. It must not win only because its direct cost is
zero.

## Key Relationships

- `service` is the main join key across logs, metrics, traces, topology, and
  action params.
- `trigger_alert.service` is an investigation starting point, not a root-cause
  guarantee.
- Trace edges identify suspicious downstream or leaf services during cascades.
- Raw live logs must be normalized into templates before comparison with
  historical `log_signatures`.
- Metric keys must be split into `service` and `metric`.
- Historical `actions_taken` must be parsed into the schema from `actions.yaml`.
- Similar historical incidents with successful outcomes should vote more
  strongly than partial or failed outcomes.
