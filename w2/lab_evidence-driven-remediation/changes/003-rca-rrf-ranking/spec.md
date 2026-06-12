# 003 - RCA RRF Ranking Spec

## Goal

Rank likely root-cause service candidates for each correlated alert cluster.

This layer answers:
- Which services are plausible root-cause candidates for this cluster?
- Which candidates are supported by graph structure, timing, and causal-lag
  evidence?
- How strong is the fused ranking, and how close are the top candidates?
- What structured RCA evidence should a later LLM layer consume?

This layer does not answer:
- Which historical incidents are similar.
- Which remediation action should be selected.
- Whether auto-remediation is safe.
- What final incident narrative should be shown to an SRE.
- What should be written to the final `audit.jsonl`.

Historical retrieval, action voting, final action selection, and submit-audit
generation belong to a later LLM-backed change.

## Position In The Pipeline

This change adds the RCA layer after detection and correlation:

```text
incident JSON
-> features.py
-> correlation.py
-> rca.py
-> later LLM retrieval / decision / audit layer
```

Layer responsibilities in this change:
- `features.py`: normalize raw metrics and logs into evidence candidates.
- `correlation.py`: group evidence into correlated alert clusters.
- `rca.py`: rank root-cause service candidates with PageRank, timestamp,
  causal-lag, and RRF.

Do not add `retrieval.py`, deterministic action voting, or `engine.py decide`
in this change.

## Input

The RCA ranker reads one live incident JSON and may read outputs from the two
previous layers:

- Detection output from `features.py`.
- Correlation output from `correlation.py`.

Incident fields used:
- `incident_id`
- `detected_at`
- `topology.nodes`
- `topology.edges`
- `traces`
- `metrics_window.samples`

Detection fields used:
- `schema_version`
- `incident_id`
- `evidence_candidates`

Correlation fields used:
- `schema_version`
- `incident_id`
- `clusters`

If no detection output is provided, the ranker may call
`features.detect_incident()` in memory. If no correlation output is provided,
the ranker may call `correlation.correlate_incident()` in memory. Do not
duplicate detection or correlation logic in the RCA layer.

## Public API

Add a public function:

```python
def rank_root_causes(
    incident: dict[str, Any],
    detection: dict[str, Any] | None = None,
    correlation: dict[str, Any] | None = None,
    source_file: str = "",
    rrf_k: int = 60,
    ranker_weights: dict[str, float] | None = None,
    max_lag_samples: int = 8,
    min_corr: float = 0.55,
) -> dict[str, Any]:
    ...
```

Default ranker weights:

```text
pagerank = 0.40
timestamp = 0.35
causal_lag = 0.25
```

## Output

The ranker returns one object:

```json
{
  "schema_version": "1.0",
  "incident_id": "E01",
  "params": {
    "rrf_k": 60,
    "ranker_weights": {
      "pagerank": 0.4,
      "timestamp": 0.35,
      "causal_lag": 0.25
    },
    "max_lag_samples": 8,
    "min_corr": 0.55
  },
  "root_cause_rankings": []
}
```

Each cluster ranking must include:
- `cluster_id`
- `services`
- `active_rankers`
- `confidence`
- `candidates`
- `warnings`

Each candidate must include:
- `rank`
- `service`
- `rrf_score`
- `normalized_score`
- `ranker_ranks`
- `ranker_scores`
- `evidence_ids`
- `explanation_signals`

Example:

```json
{
  "cluster_id": "corr:E01:s001:g001",
  "services": ["checkout-svc", "payment-svc"],
  "active_rankers": ["pagerank", "timestamp", "causal_lag"],
  "confidence": {
    "gap_ratio": 0.34,
    "level": "high"
  },
  "candidates": [
    {
      "rank": 1,
      "service": "payment-svc",
      "rrf_score": 0.0161,
      "normalized_score": 1.0,
      "ranker_ranks": {
        "pagerank": 1,
        "timestamp": 1,
        "causal_lag": 1
      },
      "ranker_scores": {
        "pagerank": 0.47,
        "timestamp": 1.0,
        "causal_lag": 2.0
      },
      "evidence_ids": [
        "metric:E01:payment-svc.cpu",
        "log:E01:payment-svc:0b879767bd"
      ],
      "explanation_signals": [
        "high_pagerank_downstream_dependency",
        "earliest_metric_degradation",
        "metric_leads_related_service"
      ]
    }
  ],
  "warnings": []
}
```

Low RCA confidence must not be hidden. It should be explicit in the RCA output
so the later LLM layer can treat close candidates conservatively.

## Candidate Set

For each correlation cluster, the candidate set is the sorted unique service
list from the cluster.

If the cluster has no services, fall back to services from its evidence
candidates. If no services can be recovered, emit an empty candidate list and a
warning.

Only rank services. Do not rank metrics, log templates, traces, actions, or
root-cause classes.

## PageRank Ranker

Build a directed service graph from:
- `incident.topology.edges`
- live `incident.traces`

Edge direction must be `caller -> callee`.

Reasoning:
- In this lab schema, topology edge `A -> B` means service `A` calls service
  `B`.
- For RCA, dependency signal should flow toward downstream services, because a
  downstream failure can propagate impact back to callers.
- Therefore PageRank should run on the caller-to-callee graph, not on the
  reversed graph.

Implementation rules:
- Add every topology node, every trace endpoint, and every cluster service as a
  graph node.
- Use trace edges to augment the static topology, matching the behavior of
  `correlation.py`.
- Run PageRank on the directed graph relevant to the cluster.
- Final ranking includes only cluster candidate services.
- Sort by PageRank score descending, then service name ascending for ties.

## Timestamp Ranker

Rank services by earliest observed degradation time.

For metric evidence:
- Split samples by `incident.detected_at`.
- Use samples before `detected_at` as baseline.
- Compute baseline mean and population standard deviation.
- A metric that worsens upward degrades when z-score is at least `3.0`.
- A metric that worsens downward degrades when z-score is at most `-3.0`.
- Reuse the local metric-direction convention from `features.py` where
  practical.

For services without usable metric degradation:
- Fall back to earliest evidence timestamp from detection candidates in the
  cluster.

Sort earlier degradation times first. Break ties by stronger candidate evidence
score, then service name.

## Causal-Lag Ranker

Use cross-correlation lag as the v1 causal signal.

Do not use Granger causality in this change. Granger is useful for offline
analysis but is too brittle for this v1 realtime-style layer because it needs
longer stationary time series and stronger statistical assumptions.

Implementation rules:
- Build one anomaly series per service from usable metric samples in the
  cluster.
- Compare service pairs with equal-length series.
- Scan lags from `-max_lag_samples` to `+max_lag_samples`.
- Compute Pearson correlation for each lag using overlapping windows.
- If the best absolute correlation is below `min_corr`, ignore that pair.
- If best lag is positive, the first service leads the second service.
- If best lag is negative, the second service leads the first service.
- If best lag is zero, treat the pair as simultaneous and do not assign a
  causal win.

Score each service by the number and strength of directional wins. Sort by
causal-lag score descending, then service name.

If fewer than two services have usable metric series, skip this ranker for that
cluster and include a warning such as:

```text
causal_lag_skipped_insufficient_metric_series
```

## Reciprocal Rank Fusion

Do not combine raw ranker scores directly.

Use Reciprocal Rank Fusion:

```text
rrf_score(service) = sum(weight_m * 1 / (rrf_k + rank_m(service)))
```

Rules:
- Default `rrf_k` is `60`.
- Use one-based ranks.
- Include only rankers that produced a valid ranking for the cluster.
- Preserve configured weights in `params`.
- If a ranker is skipped, do not add a zero score for that ranker.
- Sort fused candidates by `rrf_score` descending, then service name ascending.
- Normalize final scores by dividing by the highest fused score in the cluster.

RRF is required because PageRank, timestamp, and causal-lag scores have
different scales and meanings. Fusion must reflect ranker agreement, not raw
score magnitude.

## Confidence Gap

For each cluster:

```text
gap_ratio = (score_top1 - score_top2) / score_top1
```

Confidence levels:
- `high`: `gap_ratio > 0.30`
- `medium`: `0.10 <= gap_ratio <= 0.30`
- `low`: `gap_ratio < 0.10`

If there is only one candidate, set `gap_ratio` to `1.0` and `level` to
`high`, while preserving warnings that describe weak input evidence if any.

## CLI

Add a standalone RCA command:

```powershell
python rca.py --incident data-pack/eval/E01.json `
  --evidence artifacts/detection/E01_evidence_candidates.json `
  --correlation artifacts/correlation/E01_alert_clusters.json `
  --output artifacts/rca/E01_root_causes.json
```

Arguments:
- `--incident`: required path to one eval incident JSON.
- `--evidence`: optional path to detection output JSON.
- `--correlation`: optional path to correlation output JSON.
- `--output`: optional path for RCA output JSON.
- `--rrf-k`: optional integer, default `60`.
- `--max-lag-samples`: optional integer, default `8`.
- `--min-corr`: optional float, default `0.55`.

When `--output` is omitted, print JSON to stdout only. When `--output` is
provided, write the same JSON to the file and also print it to stdout.

## Acceptance Criteria

- RCA can run on eval incidents `E01` through `E08`.
- RCA output is deterministic across repeated runs.
- E01 ranks `payment-svc` above `checkout-svc`.
- E06 ranks `cart-svc` above `payment-svc`.
- E08 ranks `t24-service` above `bb-edge`.
- RRF uses ranks, not raw score addition.
- Ranker outputs and skipped-ranker warnings are visible in the output.
- This layer does not perform historical similarity or retrieval.
- This layer does not select remediation actions.
- This layer does not write `audit.jsonl`.
- This layer does not require LLM access.
