# 001 - Detection & Triage Tasks

## Implementation

- [ ] Add incident loading helpers.
- [ ] Add shared `EvidenceCandidate` data structure.
- [ ] Implement metric series parsing and baseline split.
- [ ] Implement metric anomaly scoring.
- [ ] Implement log normalization.
- [ ] Implement log template grouping.
- [ ] Implement log anomaly scoring.
- [ ] Emit `evidence_candidates` with source references.

## Validation

- [ ] Run detection on `eval/E01.json`.
- [ ] Verify metric candidates include abnormal payment latency/pool signals.
- [ ] Verify log candidates include repeated operational error templates.
- [ ] Run detection on all `E01` through `E08`.
- [ ] Confirm each score is within `[0, 1]`.
- [ ] Confirm every candidate includes `source_ref`.

## Documentation

- [ ] Document any threshold changes in `FINDINGS.md`.
- [ ] Add a short README note for running the detector if a standalone command is
      introduced.
