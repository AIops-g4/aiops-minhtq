# 001 - Detection & Triage Spec

## Goal

Transform raw metrics and logs from each incident into a unified list of
suspicious evidence candidates.

This layer answers:
- Which service/metric pairs look abnormal?
- Which service log templates look abnormal?
- Which evidence can be traced back to the source incident JSON?

This layer does not answer:
- Which alerts belong to the same incident cluster?
- Which service is the root cause?
- Which historical incidents are similar?
- Which remediation action should be selected?

## Input

The detector reads one live incident JSON:

- `metrics_window.samples`
- `logs`
- `detected_at`
- `trigger_alert`

The source is always the lab incident JSON. Do not assume Prometheus, Loki, or
OpenTelemetry are available.

## Output

The detector returns one object:

```json
{
  "schema_version": "1.0",
  "incident_id": "E01",
  "evidence_candidates": []
}
```

Each evidence candidate must use this envelope:

```json
{
  "schema_version": "1.0",
  "evidence_id": "metric:E01:payment-svc.latency_p99_ms",
  "evidence_type": "metric",
  "incident_id": "E01",
  "service": "payment-svc",
  "detected_at": "2026-06-10T14:23:00Z",
  "timestamp_start": "2026-06-10T14:08:00Z",
  "timestamp_end": "2026-06-10T15:22:15Z",
  "score": 0.91,
  "score_meaning": "0..1, higher means more suspicious",
  "summary": "payment-svc latency_p99_ms increased after alert",
  "signals": ["metric_increase", "latency_anomaly", "post_alert"],
  "source_ref": {
    "system": "incident_json",
    "file": "eval/E01.json",
    "path": "metrics_window.samples.payment-svc.latency_p99_ms"
  },
  "details": {}
}
```

Required candidate fields:
- `schema_version`
- `evidence_id`
- `evidence_type`
- `incident_id`
- `service`
- `detected_at`
- `timestamp_start`
- `timestamp_end`
- `score`
- `score_meaning`
- `summary`
- `signals`
- `source_ref`
- `details`

## Score Convention

All detector scores must be normalized to `[0, 1]`.

Interpretation:
- `0.00 - 0.30`: weak or likely background noise.
- `0.30 - 0.60`: notable but not strong.
- `0.60 - 0.80`: clearly suspicious.
- `0.80 - 1.00`: very suspicious and should rank near the top.

Do not store raw z-scores, counts, or burst values directly in `score`. Keep raw
debug values inside `details`.

## Metric Anomaly Detection

For each metric series:

1. Split key `service.metric` into `service` and `metric`.
2. Sort samples by timestamp.
3. Convert values to floats.
4. Split baseline and post-alert windows using `detected_at`.
5. If there are not enough pre-alert samples, use the first 30% of the window as
   baseline.
6. Compute baseline and post-alert statistics.
7. Emit a metric evidence candidate when the normalized anomaly score is high
   enough to be useful.

Recommended metric features:
- `baseline_mean`
- `baseline_std`
- `baseline_median`
- `baseline_mad`
- `start_value`
- `end_value`
- `min_value`
- `max_value`
- `absolute_delta`
- `ratio`
- `slope`
- `post_alert_peak_z`

Recommended anomaly signals:
- `metric_increase`
- `metric_decrease`
- `metric_spike`
- `latency_anomaly`
- `error_rate_anomaly`
- `memory_anomaly`
- `pool_anomaly`
- `replication_lag_anomaly`
- `post_alert`

Suggested detection rules:
- Spike/drop: `abs(z) >= 3.0` or `abs(robust_z) >= 3.5`.
- Drift: large ratio, clear slope, or large end value shift from baseline.
- Operational metrics such as latency, error rate, memory, GC pause, pool usage,
  and replica lag should receive stronger suspicion when they worsen.

## Log Mining, Parsing, And Log Anomaly Detection

Raw `logs[*].msg` must not be compared directly with historical signatures.
Normalize and template logs first.

For each log line:

1. Keep `ts`, `svc`, `level`, and raw `msg`.
2. Normalize dynamic tokens:
   - numbers -> `<num>`
   - durations such as `5000ms` or `12s` -> `<duration>`
   - percentages -> `<percent>`
   - IDs, order IDs, product IDs, revisions, attempts -> `<id>`
   - paths or endpoints -> `<path>`
   - versions such as `v3.1` -> `<version>`
3. Preserve operational keywords such as `ConnectionPool`, `timeout`,
   `pool exhausted`, `OutOfMemoryError`, `TLS`, `DNS`, `NXDOMAIN`, `throttled`,
   and `replica lag`.
4. Group similar messages into templates.
5. Aggregate by `svc`, `level`, and template.
6. Emit suspicious log evidence candidates.

Drain3 may be used for template mining when available. If it is not available in
the Conda environment, use a deterministic rule-based fallback that preserves
the same output schema.

Recommended log features:
- `template_id`
- `template`
- `svc`
- `level`
- `count`
- `first_seen`
- `last_seen`
- `burst_score`
- `keyword_score`
- `raw_indices`
- `raw_examples`

Recommended log score components:
- `severity_score`
- `frequency_score`
- `burst_score`
- `keyword_score`
- `metric_link_score`

Suggested formula:

```text
log_suspicion_score =
  0.25 * severity_score +
  0.20 * frequency_score +
  0.20 * burst_score +
  0.25 * keyword_score +
  0.10 * metric_link_score
```

Severity defaults:
- `ERROR = 1.0`
- `WARN = 0.6`
- `INFO = 0.2`

## Metric And Log Relationship

Metrics answer which service/metric pairs changed abnormally.

Logs answer which services emitted abnormal operational messages.

This change may link them lightly through:
- `details.linked_metric_anomalies`
- `signals` such as `metric_linked`

This light link is only a local service-level hint. Do not implement alert
correlation, root-cause inference, causal direction, historical retrieval, or
action selection in this change.

## Artifacts

Useful intermediate artifacts:
- `evidence_candidates.json`
- `metric_anomalies.json`
- `parsed_logs.jsonl`
- `suspicious_logs.json`

Artifacts should be debug aids. The required grading contract remains
`audit.jsonl`.

## Acceptance Criteria

- Every eval incident can produce an `evidence_candidates` list.
- Metric and log candidates use the same envelope.
- All scores are normalized to `[0, 1]`.
- Every candidate has `schema_version` and `source_ref`.
- Log candidates are based on templates, not raw messages alone.
- Noisy routine logs rank low.
- Operational error patterns such as pool exhaustion, OOM, TLS failure, DNS
  failure, throttling, and replica lag rank high.
- Output can be consumed by alert correlation and later reasoning layers.
