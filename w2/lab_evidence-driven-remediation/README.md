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

Run RCA root-cause ranking for one incident:

```bash
python rca.py --incident data-pack/eval/E01.json \
  --evidence artifacts/detection/E01_evidence_candidates.json \
  --correlation artifacts/correlation/E01_alert_clusters.json \
  --output artifacts/rca/E01_root_causes.json
```

The command combines PageRank, metric degradation timestamp ranking, and
cross-correlation lag ranking with Reciprocal Rank Fusion. RCA outputs for
E01-E08 are stored in `artifacts/rca/`.

Run the final Groq LLM-augmented remediation decision stage:

```bash
pip install -r requirements.txt
python engine.py decide --incident data-pack/eval/E01.json \
  --history data-pack/incidents_history.json \
  --actions data-pack/actions.yaml
```

The engine reads `GROQ_API_KEY` from `.env` when available, writes final outputs
under `artifacts/remediation/`, and falls back to deterministic RCA/history
guardrails if the LLM is disabled, unavailable, or disagrees with safety
checks. Use `--llm-mode off` to exercise the fallback path. The grading audit is
`artifacts/remediation/audit.jsonl`.

Run all eval incidents and grade:

```bash
rm -f artifacts/remediation/audit.jsonl
for i in 01 02 03 04 05 06 07 08; do
  python engine.py decide --incident data-pack/eval/E$i.json \
    --history data-pack/incidents_history.json \
    --actions data-pack/actions.yaml
done
python data-pack/grade.py --audit artifacts/remediation/audit.jsonl \
  --expected data-pack/eval/expected.json
```
