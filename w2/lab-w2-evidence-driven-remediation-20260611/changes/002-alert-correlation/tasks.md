# 002 - Alert Correlation Tasks

## Implementation

- [x] Add `correlation.py` with typed public function `correlate_incident()`.
- [x] Add evidence candidate loading and optional in-memory detection fallback.
- [x] Convert evidence candidates into internal alert-like records.
- [x] Implement stable timestamp parsing and deterministic sorting.
- [x] Implement time session grouping with configurable `gap_sec`.
- [x] Build topology graph from incident topology.
- [x] Augment topology graph with live trace edges.
- [x] Use `networkx` shortest-path lookup for service distances.
- [x] Implement topology grouping with configurable `max_hop`.
- [x] Implement stable evidence fingerprints.
- [x] Emit cluster summaries with scores, signals, fingerprints, evidence IDs,
      top evidence, and minimal topology details.
- [x] Add CLI options for `--incident`, `--evidence`, `--output`, `--gap-sec`,
      `--max-hop`, and `--min-score`.
- [x] Create `artifacts/correlation/` outputs only when the CLI is run with
      `--output`.
- [x] Avoid root-cause, causal-direction, remediation, or LLM narrative logic in
      this layer.

## Validation

- [x] Run correlation on `eval/E01.json` using generated detection output.
- [x] Verify E01 groups `payment-svc` and `checkout-svc` evidence together.
- [x] Run correlation on `eval/E08.json`.
- [x] Verify E08 groups `bb-edge`, `datapower`, `esb`, and `t24-service` when
      trace augmentation is enabled.
- [x] Run correlation on all `E01` through `E08`.
- [x] Confirm every retained evidence candidate appears exactly once.
- [x] Confirm time sessions use `detected_at` as the anchor and record
      `params.time_anchor_field`.
- [x] Confirm cluster IDs are deterministic across repeated runs.
- [x] Compare `gap_sec=120` and `gap_sec=300` on E01-E08 and document whether
      the outputs differ.
- [x] Confirm no score fields fall outside `[0, 1]`.
- [x] Confirm disconnected services remain separate when no topology or trace
      path exists within `max_hop`.
- [x] Confirm `max_score` and `mean_score` are used only as cluster summaries,
      not as action confidence.

## Documentation

- [x] Update `FINDINGS.md` with the chosen `gap_sec`, `max_hop`, and
      `min_score` rationale after implementation validation.
- [x] Add a README note for running `correlation.py` if the standalone CLI is
      introduced.
- [x] Record any eval incident where trace augmentation changes the cluster
      result.
