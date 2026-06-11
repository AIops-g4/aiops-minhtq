# Detection Threshold Notes

Change `001-detection-triage` adds `features.py`, which emits normalized
metric and log evidence candidates.

Metric candidates are emitted at score `>= 0.35`. The score is the maximum of
normalized peak z-score, robust z-score, drift, ratio shift, and slope shift,
with a `+0.12` boost for operational metrics such as latency, error rate,
memory, pool, TLS, DNS, throttling, and replication lag. Raw z-scores and
ratios remain in `details`.

Log candidates are emitted at score `>= 0.28`. The score combines severity,
frequency, burst rate, operational keyword matches, and a light metric-service
link. Routine INFO templates can appear as weak candidates when they are very
frequent, but operational ERROR/WARN templates such as pool exhaustion, TLS
failure, DNS failure, throttling, OOM, and replica lag rank higher.

Validation on `eval/E01.json` produced high-ranking `payment-svc` metric
anomalies and repeated `ConnectionPool` / `pool exhausted` log templates.
Validation across `E01` through `E08` produced at least one candidate per
incident, with every score in `[0, 1]` and every candidate carrying
`schema_version`, `detected_at`, and `source_ref`.

# Alert Correlation Notes

Change `002-alert-correlation` adds `correlation.py`, which consumes the
`evidence_candidates` output from `features.py` and groups it by time proximity
and service topology.

Correlation defaults are `gap_sec = 300`, `max_hop = 2`, and `min_score = 0.28`.
The time-window anchor is `detected_at`, not `timestamp_start`. This avoids
treating the beginning of a metric observation window as the anomaly time.
`timestamp_start` and `timestamp_end` remain in the output as the source
evidence range for audit.

`gap_sec = 300` keeps incident evidence together while allowing metric, log, and
trace evidence to arrive slightly out of phase across incidents. On E01-E08,
`gap_sec = 120` and `gap_sec = 300` produced the same cluster shapes because all
retained evidence in each incident shares the same `detected_at`. `max_hop = 2`
captures short local cascades without treating the whole graph as related.
`min_score = 0.28` preserves all evidence that the detection layer already
emitted.

Trace augmentation matters for E03 and E08. Without live trace edges, E03 splits
into separate `esb` and `datapower` clusters, and E08 splits into separate
`bb-edge`, `datapower`, `esb`, and `t24-service` clusters. With trace-augmented
topology, E03 becomes one `datapower/esb` cluster and E08 becomes one cascade
cluster across all four runtime services.

Validation across E01-E08 produced one correlation output per incident in
`artifacts/correlation/`. Every retained evidence candidate appears exactly once
in a cluster, cluster output is deterministic across repeated runs, and
`max_score` / `mean_score` stay within `[0, 1]`. These scores are cluster
suspiciousness summaries only; they are not remediation confidence.
