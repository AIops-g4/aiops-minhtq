# 003 - RCA RRF Ranking Tasks

## Implementation

- [x] Add `rca.py` with typed public function `rank_root_causes()`.
- [x] Add JSON loaders for optional detection and correlation artifacts.
- [x] Call `features.detect_incident()` in memory when detection input is
      omitted.
- [x] Call `correlation.correlate_incident()` in memory when correlation input
      is omitted.
- [x] Build per-cluster service candidate sets from correlation clusters.
- [x] Implement directed service graph construction using topology and live
      trace edges.
- [x] Implement PageRank ranking with `caller -> callee` edge direction.
- [x] Implement metric degradation-time extraction for timestamp ranking.
- [x] Implement evidence timestamp fallback for services without usable metric
      degradation.
- [x] Implement anomaly-series construction for causal-lag ranking.
- [x] Implement pairwise cross-correlation lag scanning with configurable
      `max_lag_samples` and `min_corr`.
- [x] Skip causal-lag ranking with an explicit warning when metric series are
      insufficient or inconclusive.
- [x] Implement Reciprocal Rank Fusion with default `rrf_k = 60`.
- [x] Record active rankers, per-ranker ranks, per-ranker scores, fused scores,
      normalized scores, confidence gap, and warnings.
- [x] Add standalone RCA CLI options for `--incident`, `--evidence`,
      `--correlation`, `--output`, `--rrf-k`, `--max-lag-samples`, and
      `--min-corr`.
- [x] Create `artifacts/rca/` outputs only when the RCA CLI is run with
      `--output`.
- [x] Avoid historical retrieval, action selection, audit writing, and LLM
      narrative logic in this layer.

## Validation

- [x] Run RCA on `eval/E01.json` using generated detection and correlation
      outputs.
- [x] Verify E01 ranks `payment-svc` above `checkout-svc`.
- [x] Run RCA on `eval/E06.json`.
- [x] Verify E06 ranks `cart-svc` above `payment-svc`.
- [x] Run RCA on `eval/E08.json`.
- [x] Verify E08 ranks `t24-service` above `bb-edge`.
- [x] Run RCA on all `E01` through `E08`.
- [x] Confirm RCA output is deterministic across repeated runs.
- [x] Confirm every fused candidate has `rank`, `service`, `rrf_score`,
      `normalized_score`, `ranker_ranks`, `ranker_scores`, `evidence_ids`, and
      `explanation_signals`.
- [x] Confirm `confidence.gap_ratio` and `confidence.level` are present for
      every cluster ranking.
- [x] Confirm skipped rankers produce warnings instead of hidden failures.
- [x] Confirm no RCA score fields are negative.
- [x] Confirm `rca.py` prints JSON to stdout when `--output` is omitted.
- [x] Confirm `rca.py` writes JSON and prints the same payload when `--output`
      is provided.
- [x] Confirm `audit.jsonl` is not written by this layer.

## Tests

- [ ] Add a focused test that RRF fusion is rank-based and insensitive to raw
      score scale.
- [ ] Add a focused test that PageRank direction favors downstream dependency
      candidates for a simple `edge -> checkout -> payment` graph.
- [ ] Add a focused test that timestamp ranking prefers earliest metric
      degradation over alert firing time.
- [ ] Add a focused test that causal-lag ranking skips when fewer than two
      usable metric series exist.
- [ ] Add a focused test that confidence gap is `low` when top candidates are
      close.

## Documentation

- [x] Update `FINDINGS.md` with the RCA ranker design and why RRF is used.
- [x] Document why cross-correlation lag is used in v1 instead of Granger
      causality.
- [x] Document that historical retrieval, action selection, and final audit
      generation are deferred to the later LLM layer.
- [x] Add a README note for running `rca.py` if the standalone CLI is
      introduced.
- [x] Record any eval incident where rankers disagree and the RRF result is
      intentionally low-confidence.
