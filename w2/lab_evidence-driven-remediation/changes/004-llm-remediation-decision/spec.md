# 004 - LLM Remediation Decision Spec

## Goal

Select a final remediation action from RCA candidates, historical precedents,
action metadata, and optional LLM reasoning.

This layer answers:
- Which action should the engine recommend for the incident?
- Which root-cause service does that action target?
- How confident is the decision?
- What evidence and historical precedents justify the decision?
- Was the final recommendation produced by the LLM or by a guardrail fallback?

This layer does not answer:
- How to execute a remediation action.
- How to update the historical corpus.
- How to stream or deploy the system.

## Position In The Pipeline

This change adds the final stage:

```text
incident JSON
-> features.py
-> correlation.py
-> rca.py
-> engine.py decision / LLM / audit layer
```

Layer responsibilities:
- `features.py`: emit normalized metric/log evidence candidates.
- `correlation.py`: group evidence into incident clusters.
- `rca.py`: rank likely root-cause services.
- `engine.py`: retrieve similar history, vote actions, call/validate LLM, apply
  guardrails, and write decision artifacts.

## Input

The CLI reads:
- One incident JSON from `data-pack/eval/E*.json`.
- Historical incidents from `data-pack/incidents_history.json`.
- Action catalog from `data-pack/actions.yaml`.
- Optional `.env` with `GROQ_API_KEY`.

The LLM prompt includes:
- Incident id, alert service, and severity.
- Top RCA candidates and per-ranker evidence.
- Correlated cluster top evidence and dominant signals.
- Top 3 retrieved historical incidents.
- Outcome-weighted action votes.
- Valid actions from the action catalog.

## Public CLI

Add:

```powershell
python engine.py decide --incident data-pack/eval/E01.json `
  --history data-pack/incidents_history.json `
  --actions data-pack/actions.yaml `
  --artifacts-dir artifacts `
  --model openai/gpt-oss-20b `
  --llm-mode auto
```

Arguments:
- `--incident`: required path to one incident JSON.
- `--history`: optional path, default `data-pack/incidents_history.json`.
- `--actions`: optional path, default `data-pack/actions.yaml`.
- `--artifacts-dir`: optional output root, default `artifacts`.
- `--model`: optional Groq model, default `openai/gpt-oss-20b`.
- `--llm-mode`: `auto`, `required`, or `off`; default `auto`.

The command prints the final decision JSON to stdout and appends one JSONL line
to `artifacts/remediation/audit.jsonl`.

## Output

Each final decision must include at minimum:

```json
{
  "schema_version": "1.0",
  "incident_id": "E01",
  "selected_action": "rollback_service",
  "params": {
    "service": "payment-svc",
    "target_version": "previous"
  },
  "confidence": 0.8316,
  "evidence": {}
}
```

The evidence block should include:
- `method`: `llm-augmented`, `llm-guarded-fallback`,
  `llm-error-fallback`, `llm-missing-key-fallback`, or `llm-off-fallback`.
- `reasoning`: short explanation of the final decision path.
- `root_cause_service` and `root_cause_class`.
- `rca_top_candidates`.
- `top_3_neighbors`.
- `action_votes`.
- `dominant_signals`.
- `blast_radius_check`.
- `llm_evidence` when an LLM response was available.

For audit convenience, `top_3_neighbors`, `consensus_score`, and
`blast_radius_check` may also be duplicated at the top level.

## Retrieval And Voting

Retrieve top historical incidents using a compact hybrid similarity:
- service overlap,
- log keyword overlap,
- trace-edge overlap,
- small bonus when the RCA top service appears in the historical affected
  services.

Action votes are weighted by:

```text
vote = similarity * outcome_weight
```

Outcome weights:
- `success = 1.0`
- `partial = 0.55`
- `failed = 0.1`

Historical `actions_taken` strings must be parsed into the `actions.yaml`
schema. Service-targeted actions are mapped onto the current RCA top service
instead of blindly reusing the historical service.

## LLM And Guardrails

The LLM is a final summarization and classification helper. It must not replace
RCA ranking.

LLM validation rules:
- `root_cause_service` must be one of the RCA candidate services.
- `selected_action` must exist in `actions.yaml`.
- Required action params must be present after normalization.
- `rollback_service` defaults `target_version` to `previous`.
- `confidence` must be in `[0, 1]`.

Fallback rules:
- If LLM mode is `off`, use deterministic fallback.
- If Groq is unavailable, returns invalid JSON, or violates validation, use
  deterministic fallback.
- If the LLM suggests an action that conflicts with safety guardrails, keep the
  LLM response artifact but select the guarded fallback decision.
- Conflicting pool evidence should escalate instead of auto-applying a pool
  action to the wrong RCA service.
- Novel or weak historical support should escalate instead of guessing.

## Artifacts

For each incident, write:
- `artifacts/remediation/<ID>_decision.json`
- `artifacts/remediation/<ID>_llm_prompt.json`
- `artifacts/remediation/<ID>_llm_response.json`

Append:
- `artifacts/remediation/audit.jsonl`

Never write secrets such as `GROQ_API_KEY` into artifacts.

## Acceptance Criteria

- `engine.py decide` runs on E01 through E08.
- `artifacts/remediation/audit.jsonl` contains one entry per eval incident.
- The provided grader reports no missing incidents.
- The provided grader reports no `must_not_action` violations.
- The final grader result reaches at least 5/8 correct; current validation is
  8/8 correct.
- LLM prompt and response artifacts are written for auditability.
- The final decision remains reproducible with `--llm-mode off`.
- `.env` is read but not committed or copied into artifacts.
