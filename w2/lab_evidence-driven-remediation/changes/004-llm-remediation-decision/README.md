# 004 - LLM Remediation Decision

This change completes the lab pipeline by adding the final remediation decision
layer after RCA.

Scope:
- Run detection, correlation, RCA, history retrieval, action voting, optional
  Groq LLM summarization, validation, and final audit generation from one CLI.
- Use the existing `.env` `GROQ_API_KEY` when LLM mode is enabled.
- Write final decision artifacts under `artifacts/remediation/`.
- Preserve deterministic fallback behavior when the LLM is disabled,
  unavailable, invalid, or conflicts with safety guardrails.

Out of scope:
- Executing remediation actions.
- Mutating files under `data-pack`.
- Replacing graph/RCA ranking with an LLM-only decision.
- Streaming, UI, or service deployment.

Expected command:

```powershell
python engine.py decide --incident data-pack/eval/E01.json `
  --history data-pack/incidents_history.json `
  --actions data-pack/actions.yaml
```

Final outputs:
- `artifacts/remediation/E01_decision.json`
- `artifacts/remediation/E01_llm_prompt.json`
- `artifacts/remediation/E01_llm_response.json`
- `artifacts/remediation/audit.jsonl`

The audit file is the grader input:

```powershell
python data-pack/grade.py --audit artifacts/remediation/audit.jsonl `
  --expected data-pack/eval/expected.json
```
