# ADR-001: Use Topology-Aware RCA With Change-Event Correlation

## Status
accepted

## Context
The AWS S3 reproduction showed that a narrow-looking maintenance action can create simultaneous symptoms across billing-control, s3-index, and s3-placement. The current detector can alert quickly on multi-service disappearance, but the postmortem detection gaps show weak audit/change-event correlation and limited command-scope evidence. RCA must separate a broad operational blast radius from an ordinary infrastructure failure.

## Decision
The AIOps platform will use topology-aware RCA enriched with change-event correlation for control-plane incidents.

## Alternatives considered
1. **Count-based RCA**
   - **Pros:** Simple to implement, explainable, fast for noisy incidents.
   - **Cons:** Selects the loudest symptom rather than the causal component; would likely blame s3-index or s3-placement instead of the maintenance command scope.

2. **Pure causal-lag RCA**
   - **Pros:** Good at ranking signals that appear before downstream symptoms; useful for latency and retry cascades.
   - **Cons:** Needs high-quality timestamps and enough event density; command/audit events can be missed if they are not modeled as first-class evidence.

3. **Topology-aware RCA with change-event correlation**
   - **Pros:** Uses dependency edges plus audit/change windows, which directly addresses the observed gap where maintenance scope explains simultaneous service loss.
   - **Cons:** Requires maintaining service topology and change-event ingestion; bad topology data can bias RCA.

## Consequences
- **Positive:** RCA can explain why billing-control, s3-index, and s3-placement failed together instead of treating each alert as an independent outage.
- **Negative:** The platform must ingest deploy, audit, and maintenance events with reliable timestamps.
- **Risks introduced:** Missing or stale topology can produce confident but wrong root-cause ranking.
- **What gets locked in:** Future detectors and dashboards need a common event schema for service topology, alerts, and change windows.
