# 002 - Alert Correlation

This change introduces the second engine layer: grouping suspicious evidence
candidates into correlated alert clusters.

Scope:
- Time-window session grouping over detection evidence candidates.
- Service-topology grouping inside each time session.
- Trace-augmented topology for services missing from the static topology.
- Cluster summaries that later retrieval and decision layers can consume.

Out of scope:
- Historical incident retrieval.
- Outcome-weighted action voting.
- Final cost/risk-aware action selection.
- Streaming or incremental alert processing.
