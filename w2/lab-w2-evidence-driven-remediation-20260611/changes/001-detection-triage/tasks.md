# 001 - Detection & Triage Tasks

## Implementation

- [x] Add incident loading helpers.
- [x] Add shared `EvidenceCandidate` data structure.
- [x] Implement metric series parsing and baseline split.
- [x] Implement metric anomaly scoring.
- [x] Implement log normalization.
- [x] Implement log template grouping.
- [x] Implement log anomaly scoring.
- [x] Emit `evidence_candidates` with source references.
- [x] Avoid alert clustering, root-cause inference, historical matching, and
      action-selection logic in this layer.

## Validation

- [x] Run detection on `eval/E01.json`.
- [x] Verify metric candidates include abnormal payment latency/pool signals.
- [x] Verify log candidates include repeated operational error templates.
- [x] Run detection on all `E01` through `E08`.
- [x] Confirm each score is within `[0, 1]`.
- [x] Confirm every candidate includes `detected_at`.
- [x] Confirm every candidate includes `source_ref`.

## Documentation

- [x] Document any threshold changes in `FINDINGS.md`.
- [x] Add a short README note for running the detector if a standalone command is
      introduced.
