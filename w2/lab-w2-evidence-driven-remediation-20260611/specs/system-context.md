# System Context

## Objective

Build a local Python CLI for an AIOps evidence-driven remediation engine.

The engine receives one structured incident JSON containing logs, traces,
metrics, and topology. It returns one recommended remediation action with a
confidence score and an auditable evidence chain.

## Pipeline

```text
incident evidence
-> detection and triage features
-> historical retrieval
-> outcome-weighted action voting
-> cost/risk-aware decision
-> audit.jsonl
```

## Non-Negotiable Constraints

- Do not map `root_cause_class` directly to an action.
- Do not infer the root cause from `trigger_alert.service` alone.
- Use both logs and traces as first-class signals; metrics alone are not enough.
- Escalate with `page_oncall` only when the evidence is novel or too weak for a
  safe auto-action.
- Preserve the CLI and audit contracts described in `data-pack/HANDOUT.md`.

## Runtime Contract

The required CLI entry point is:

```powershell
python engine.py decide --incident eval/E01.json --history incidents_history.json --actions actions.yaml
```

The engine must print a JSON decision to stdout and append one JSON object per
incident to `audit.jsonl`.

The minimum audit fields are:

```json
{
  "incident_id": "E01",
  "selected_action": "rollback_service",
  "params": {"service": "payment-svc"},
  "confidence": 0.72,
  "evidence": {}
}
```

## Main Layers

1. Detection and triage: normalize raw incident evidence into comparable,
   scored signals.
2. Retrieval: compare the current incident with historical incidents.
3. Decision: rank candidate actions using similarity, historical outcome,
   confidence, cost, and blast radius.
