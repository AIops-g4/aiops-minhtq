# AIOps Remediation Submission

This directory is the clean submission workspace. The implementation reads the
provided incident files from `data-pack`, but does not modify files under
`data-pack`.

Run detection and triage for one incident from this directory:

```bash
python features.py --incident data-pack/eval/E01.json --output artifacts/detection/E01_evidence_candidates.json
```

The command prints a JSON object with `schema_version`, `incident_id`, and a
ranked `evidence_candidates` list. Each candidate includes a normalized score,
signals, details, and a `source_ref` back to the incident JSON.

Run alert correlation for one incident:

```bash
python correlation.py --incident data-pack/eval/E01.json \
  --evidence artifacts/detection/E01_evidence_candidates.json \
  --output artifacts/correlation/E01_alert_clusters.json
```

The command groups detection evidence by time proximity and service
topology/trace proximity. Correlation outputs for E01-E08 are stored in
`artifacts/correlation/`, with `alert_clusters.json` as the combined artifact.
