# 002 - Alert Correlation Spec

## Goal

Reduce many suspicious evidence candidates into a smaller set of incident
clusters that are both temporally close and topologically related.

This layer answers:
- Which suspicious metric and log evidence belongs to the same incident burst?
- Which services are close enough in the dependency graph to be treated as a
  correlated cascade?
- Which evidence IDs should be passed together to later graph, causal, and LLM
  reasoning layers?

## Input

The correlator reads one live incident JSON and one detection output from
`features.py`.

Incident fields used:
- `incident_id`
- `topology.nodes`
- `topology.edges`
- `traces`

Detection fields used:
- `schema_version`
- `incident_id`
- `evidence_candidates`

Each evidence candidate is treated as an alert-like record using:
- `evidence_id`
- `evidence_type`
- `service`
- `detected_at`
- `timestamp_start`
- `timestamp_end`
- `score`
- `signals`
- `summary`
- `details`

If no detection output is provided, the correlator may call
`features.detect_incident()` in memory. Do not duplicate detection logic in the
correlation layer.

## Relationship To 001 - Detection And Triage

This change must consume the normalized output produced by
`001-detection-triage`. It should not re-parse raw metric samples or raw log
messages for anomaly detection.

The useful contract from 001 is the common evidence envelope:

```text
evidence_id
evidence_type
service
detected_at
timestamp_start
timestamp_end
score
summary
signals
details
```

Metric and log candidates have different `details`, but they share enough
top-level fields for correlation:

- `detected_at` drives time-session grouping.
- `timestamp_start` and `timestamp_end` preserve the source evidence range.
- `service` drives topology grouping.
- `score` drives filtering and cluster ranking.
- `evidence_id` preserves traceability and exactly-once assignment.
- `summary` and `signals` explain the final cluster.
- `details.metric` and `details.template_id` produce stable fingerprints.

Do not require metric and log `signals` to overlap for clustering. Signals are
descriptive tags for cluster explanation and later retrieval. The actual
correlation decision is based on time proximity plus service/topology proximity.
For example, a metric may emit `latency_anomaly` while a related log emits
`timeout_anomaly`; those should still cluster when they occur close together on
the same or nearby services.

## Boundary With Later Graph, Causal, And LLM Layers

This change is intentionally a grouping layer, not a root-cause layer.

Do not infer:
- root cause service
- causal direction
- remediation action
- action confidence
- final incident narrative

Those belong to later graph reasoning, causal analysis, retrieval, decision, or
LLM-augmented explanation layers.

The correlation output should only preserve enough structure for those later
layers:
- which evidence candidates belong together
- which services are present in the group
- which time range the group covers
- which local topology or trace edges made the grouping possible
- compact summaries and signals for audit/debug

## Output

The correlator returns one object:

```json
{
  "schema_version": "1.0",
  "incident_id": "E01",
  "input_alerts": 9,
  "output_clusters": 1,
  "reduction_ratio": 0.8889,
  "params": {
    "gap_sec": 300,
    "max_hop": 2,
    "min_score": 0.28,
    "time_anchor_field": "detected_at"
  },
  "clusters": []
}
```

Each cluster must use this envelope:

```json
{
  "cluster_id": "corr:E01:s001:g001",
  "alert_count": 9,
  "services": ["checkout-svc", "edge-lb", "payment-svc"],
  "time_range": [
    "2026-06-10T14:08:00Z",
    "2026-06-10T15:22:15Z"
  ],
  "max_score": 1.0,
  "mean_score": 0.7512,
  "dominant_signals": ["metric_spike", "post_alert", "pool_anomaly"],
  "fingerprints": [
    "metric:payment-svc:cpu",
    "log:payment-svc:b0454ec747"
  ],
  "evidence_ids": [
    "metric:E01:payment-svc.cpu",
    "log:E01:payment-svc:0b879767bd"
  ],
  "top_evidence": [],
  "topology_details": {}
}
```

Required cluster fields:
- `cluster_id`
- `alert_count`
- `services`
- `time_range`
- `max_score`
- `mean_score`
- `dominant_signals`
- `fingerprints`
- `evidence_ids`
- `top_evidence`
- `topology_details`

Cluster IDs must be deterministic and use:

```text
corr:{incident_id}:s{session_idx:03d}:g{group_idx:03d}
```

## Parameter Defaults

Default parameters:

```text
gap_sec = 300
max_hop = 2
min_score = 0.28
```

`gap_sec = 300` is the default because this lab correlates incident evidence,
not a high-volume realtime alert stream. The current E01-E08 detection
artifacts have evidence start-time gaps below two minutes, so `gap_sec = 120`
also works for the present data. Five minutes is less brittle when log, metric,
and trace evidence arrive slightly out of phase. The implementation must expose
`gap_sec` through the public function and CLI so `120` can be used to reproduce
the earlier notebook behavior from `w2/d1/assignment.ipynb`.

`max_hop = 2` is the default because one hop is too strict for cascades such as
`edge -> checkout -> payment`, while more than two hops can pull unrelated
services through high-degree nodes or shared stores. Two hops captures local
propagation without treating the whole graph as one incident.

`min_score = 0.28` matches the current lower bound used by `features.py` for log
evidence. Correlation should not silently drop evidence that detection already
considered useful. Later retrieval or decision layers may rank clusters down,
but the correlation layer should preserve the detection layer's candidates.

## Time Session Grouping

For each candidate:

1. Ignore candidates with `score < min_score`.
2. Parse `detected_at` as UTC. If reading an older artifact without
   `detected_at`, fall back to `timestamp_start`.
3. Sort candidates by the parsed time anchor, then by `evidence_id` for stable
   ties.
4. Start the first session with the earliest candidate.
5. Add the next candidate to the current session when its anchor time is no more
   than `gap_sec` after the previous candidate's anchor time.
6. Start a new session when the gap is greater than `gap_sec`.

The gap is measured against the previous candidate in sorted order, not against
the first candidate in the session. This preserves burst chains where each
adjacent alert is close even if the full session spans longer than `gap_sec`.
`timestamp_start` and `timestamp_end` remain source evidence ranges for audit
and cluster `time_range`; they are not the session anchor.

## Topology Grouping

Inside each time session:

1. Build an undirected service graph from `incident.topology.edges`.
2. Add every topology node and every candidate service as a graph node.
3. Augment the graph with live trace edges from `incident.traces`.
4. Group candidates by service.
5. Union two services when their shortest-path distance is `<= max_hop`.
6. Always keep candidates from the same service in the same topology group.
7. Keep unknown or disconnected services as separate groups unless they share
   the same service.

Trace augmentation is required. Some eval incidents contain runtime services in
metrics, logs, and traces that are missing from the embedded static topology,
for example `datapower`, `esb`, `bb-edge`, and `t24-service`. Without trace
edges, E03 and E08 would be split incorrectly.

Use `networkx` for graph construction and shortest-path distance checks. The
lab Conda environment already provides `networkx`, so do not add a new
dependency or vendor a graph implementation.

## Fingerprints

Use stable fingerprints for cluster summaries:

```text
metric:{service}:{metric}
log:{service}:{template_id}
{evidence_type}:{service}:{stable_detail_or_evidence_suffix}
```

For metric candidates, prefer `details.metric`.

For log candidates, prefer `details.template_id`.

If neither detail exists, fall back to a stable suffix derived from
`evidence_id`. Do not include timestamp, score, or raw values in fingerprints;
those fields change per incident and would prevent duplicate-like evidence from
collapsing into the same summary.

## Cluster Summary Rules

For each final topology group:

- `services`: sorted unique service names.
- `time_range`: minimum `timestamp_start` and maximum `timestamp_end`.
- `max_score`: maximum candidate score rounded to four decimals; this is not an
  action confidence.
- `mean_score`: average candidate score rounded to four decimals; this is only
  a cluster-level suspiciousness summary.
- `dominant_signals`: most frequent signals, tie-broken alphabetically.
- `fingerprints`: sorted unique fingerprints.
- `evidence_ids`: evidence IDs sorted by candidate start time and ID.
- `top_evidence`: highest-scoring five candidates, compacted to ID, type,
  service, `detected_at`, score, summary, and signals.
- `topology_details`: include only `max_hop`, service-pair distances used for
  successful unions, and trace edges added to the graph.

Clusters should be sorted deterministically by:

1. earliest `time_range[0]`
2. descending `max_score`
3. `cluster_id`

This order is for stable output and basic triage display. It must not be treated
as root-cause ranking.

## CLI

Add a standalone command:

```powershell
python correlation.py --incident data-pack/eval/E01.json `
  --evidence artifacts/detection/E01_evidence_candidates.json `
  --output artifacts/correlation/E01_alert_clusters.json
```

Arguments:
- `--incident`: required path to one eval incident JSON.
- `--evidence`: optional path to detection output JSON.
- `--output`: optional path for correlation output JSON.
- `--gap-sec`: optional integer, default `300`.
- `--max-hop`: optional integer, default `2`.
- `--min-score`: optional float, default `0.28`.

When `--output` is omitted, print JSON to stdout only. When `--output` is
provided, write the same JSON to the file and also print it to stdout.

## Acceptance Criteria

- Every eval incident E01 through E08 can produce an alert cluster output.
- Every retained evidence candidate appears in exactly one final cluster.
- Candidate order and cluster IDs are deterministic.
- `gap_sec`, `max_hop`, and `min_score` are recorded in `params`.
- E01 groups payment and checkout evidence into the same correlated cluster.
- E08 can group `bb-edge`, `datapower`, `esb`, and `t24-service` through
  trace-augmented topology.
- Disconnected services are not merged only because they occur in the same time
  session.
- The implementation uses the existing `networkx` installation and does not add
  new dependencies.
- Output can be consumed by later retrieval and decision layers.
