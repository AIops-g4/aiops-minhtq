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

# RCA RRF Ranking Notes

Change `003-rca-rrf-ranking` adds `rca.py`, which consumes incident JSON,
detection candidates, and alert clusters to rank likely root-cause services.
The layer is intentionally RCA-only: it does not perform historical retrieval,
select remediation actions, call an LLM, or write `audit.jsonl`.

The RCA layer uses three rankers. PageRank runs on a directed service graph with
edges in `caller -> callee` direction, so dependency signal can accumulate on
downstream services. Timestamp ranking finds the first metric degradation using
a pre-alert baseline and z-score threshold `>= 3.0`, with earliest evidence time
as fallback when a service has no usable metric series. Cross-correlation lag
compares service anomaly series and gives directional wins to services whose
metric movement leads related services.

Granger causality is not used in this version. The eval incident windows are
short, Granger requires stronger stationarity and sample-size assumptions, and
its p-values are less direct to explain during realtime triage. Cross-correlation
lag is lighter, deterministic, and produces an explainable "service A leads
service B" signal that can be converted into a rank.

The final fusion uses Reciprocal Rank Fusion with `k = 60` and weights
`pagerank = 0.40`, `timestamp = 0.35`, and `causal_lag = 0.25`. RRF is used
instead of raw weighted score addition because PageRank scores, timestamp
scores, and lag-correlation scores are on different scales. Fusion should
reflect agreement between rankers, not raw score magnitude.

Validation across E01-E08 produced RCA outputs in `artifacts/rca/`. The expected
hard cases rank correctly for the RCA layer: E01 ranks `payment-svc` first, E06
ranks `cart-svc` above `payment-svc`, and E08 ranks `t24-service` first. Several
clusters have low gap confidence because top candidates are close after RRF;
that uncertainty is preserved for the later LLM decision layer rather than being
hidden.

# LLM-Augmented Remediation Notes

The final stage adds `engine.py`, which runs detection, correlation, RCA,
history retrieval, action voting, and optional Groq LLM summarization in one
CLI. All final decision artifacts are written to `artifacts/remediation/`,
including per-incident prompt/response JSON files, per-incident decision JSON
files, and `audit.jsonl`.

The LLM is deliberately last in the pipeline. It receives the top RCA
candidates, cluster evidence, top historical neighbors, and action catalog, then
returns a structured JSON recommendation. The engine validates that output
against candidate services, action names, required params, and confidence bounds.
If Groq is unavailable or the recommendation conflicts with deterministic
guardrails, the engine records `llm-error-fallback`, `llm-off-fallback`, or
`llm-guarded-fallback` and uses the safer RCA/history decision.

With `--llm-mode auto`, validation across E01-E08 produced
`Correct: 8/8`, `Forbidden: 0/8`, and `Missing: 0/8` from the provided grader
using `artifacts/remediation/audit.jsonl`. The guardrail mattered on cases where
the LLM preferred a plausible but unsafe pool-size action while RCA/history
evidence called for rollback or escalation.

# Required Reflection Answers

1. Similarity function: the final engine uses a compact hybrid score over
   service overlap, normalized log keyword overlap, and trace-edge overlap, then
   keeps the top 3 historical incidents. This was chosen over pure service
   overlap because service-only retrieval overfavored broad incidents such as
   `INC-2026-03-20` for E01, while the log/trace terms preserve concrete signals
   such as pool exhaustion, TLS failures, DNS failures, and retry/throttle
   patterns. The decision artifact records the actual neighbors and scores; for
   E08 all top neighbors have only `0.0488` similarity, which is treated as weak
   historical support rather than a strong precedent.

2. Outcome-weighted voting: historical actions are weighted by similarity and
   outcome quality (`success = 1.0`, `partial = 0.55`, `failed = 0.1`). This
   prevents failed or partial precedents from dominating just because they are
   nearby. On E05, the top neighbors are close (`0.5771`, `0.5750`, `0.5163`);
   the engine keeps the successful `rollback_service:payment-svc:previous`
   precedent as an acceptable remediation and rejects the LLM's
   `increase_pool_size` suggestion through the guardrail.

3. EV/action calculation example: E01's RCA top service is `payment-svc`
   (`normalized_score = 1.0`) with pool and timeout evidence. The action vote
   candidates include `page_oncall` (`0.7222` from broad/partial page precedents),
   `increase_pool_size` (`0.3316`), and `rollback_service` (`0.3316`). Even
   though page has the largest raw vote, the decision layer does not let
   zero-cost escalation win when pool evidence is concrete and the auto-action
   blast radius is one service. Between the two pool remediations, rollback is
   preferred as the safer guarded action in the final audit, producing
   `rollback_service` for `payment-svc` with confidence `0.8316`.

4. Escalation behavior: the engine chose `page_oncall` for E02, E06, E07, and
   E08. E02 is TLS/certificate-related and human-owned. E06 has conflicting
   evidence: RCA ranks `cart-svc` first, while the LLM and logs point toward a
   pool action on `payment-svc`, so the guardrail escalates. E07 is treated as
   novel/unsafe to auto-remediate even though history votes all point to paging.
   E08 correctly identifies `t24-service` as RCA top-1, but historical support is
   very weak (`0.0488`), so paging is safer than auto-rollback.

5. Most likely breakage: the weakest class is a novel incident whose symptoms
   share vocabulary with a known auto-remediable class. E06 is the warning case:
   pool-looking logs could have caused an unsafe `increase_pool_size`, but trace
   and RCA evidence pointed elsewhere. A stronger future improvement would add
   semantic retrieval over normalized log templates plus calibrated per-action
   success probabilities; I did not implement that here because the current
   small corpus is handled well by explainable heuristic retrieval and guardrails.
