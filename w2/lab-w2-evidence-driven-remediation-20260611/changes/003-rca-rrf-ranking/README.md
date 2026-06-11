# 003 - RCA RRF Ranking

This change introduces root-cause ranking with Reciprocal Rank Fusion and
prepares structured RCA evidence for the later LLM decision layer.

Scope:
- Rank root-cause service candidates inside each correlated alert cluster.
- Combine graph, timestamp, and causal-lag rankings with Reciprocal Rank
  Fusion.
- Return structured scores, per-ranker evidence, confidence gap, and warnings.
- Produce JSON that a later LLM layer can use for retrieval, action selection,
  and narrative generation.

Out of scope:
- Historical similarity or retrieval.
- Outcome-weighted action voting.
- Remediation action selection.
- `engine.py decide` submit integration.
- Writing `audit.jsonl`.
- LLM narrative generation.

Expected standalone command:

```powershell
python rca.py --incident data-pack/eval/E01.json `
  --evidence artifacts/detection/E01_evidence_candidates.json `
  --correlation artifacts/correlation/E01_alert_clusters.json `
  --output artifacts/rca/E01_root_causes.json
```

When `--output` is omitted, the command should print JSON to stdout only. When
`--output` is provided, it should write the same JSON to disk and print it to
stdout.

The next change should consume this RCA output in the LLM layer. That later
layer owns historical retrieval, action selection, final confidence, and
`audit.jsonl`.
