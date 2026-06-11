# 001 - Detection & Triage

This change introduces the first engine layer: converting raw incident evidence
into normalized, scored evidence candidates.

Scope:
- Metric anomaly detection.
- Log mining, parsing, and log anomaly scoring.
- A shared evidence candidate schema consumed by retrieval and decision layers.

Out of scope:
- Historical retrieval.
- Outcome-weighted action voting.
- Final cost/risk-aware action selection.
