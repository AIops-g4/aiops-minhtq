# 001 - Detection & Triage

This change introduces the first engine layer: converting raw incident evidence
into normalized, scored evidence candidates.

Scope:
- Metric anomaly detection.
- Log mining, parsing, and log anomaly scoring.
- A shared evidence candidate schema consumed by alert correlation and later
  reasoning layers.

Out of scope:
- Alert correlation and clustering.
- Graph or causal reasoning.
- LLM-augmented explanation.
- Historical retrieval.
- Outcome-weighted action voting.
- Final cost/risk-aware action selection.
