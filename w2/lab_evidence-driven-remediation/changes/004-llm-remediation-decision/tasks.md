# 004 - LLM Remediation Decision Tasks

## Implementation

- [x] Add `engine.py` with `decide` CLI command.
- [x] Call `features.detect_incident()` in memory.
- [x] Call `correlation.correlate_incident()` in memory.
- [x] Call `rca.rank_root_causes()` in memory.
- [x] Load historical incidents from `data-pack/incidents_history.json`.
- [x] Load actions from `data-pack/actions.yaml`.
- [x] Add dependency manifest in `requirements.txt`.
- [x] Read `GROQ_API_KEY` from `.env` without writing secrets to artifacts.
- [x] Build compact LLM prompt context from RCA, correlation evidence, history,
      action votes, and action catalog.
- [x] Call Groq in `--llm-mode auto`.
- [x] Support `--llm-mode off` deterministic fallback.
- [x] Validate LLM output against candidate services, action catalog, params,
      and confidence bounds.
- [x] Apply guardrail fallback when LLM output conflicts with RCA/history
      safety logic.
- [x] Write per-incident decision artifacts under `artifacts/remediation/`.
- [x] Write per-incident prompt and response artifacts under
      `artifacts/remediation/`.
- [x] Append final audit records to `artifacts/remediation/audit.jsonl`.
- [x] Keep `data-pack` read-only.

## Validation

- [x] Run E01 smoke test with `--llm-mode off`.
- [x] Run E01 smoke test with `--llm-mode auto`.
- [x] Run E01 through E08 with `--llm-mode off`.
- [x] Run E01 through E08 with `--llm-mode auto`.
- [x] Grade `artifacts/remediation/audit.jsonl` against
      `data-pack/eval/expected.json`.
- [x] Confirm final grader result is `Correct: 8/8`.
- [x] Confirm final grader reports `Forbidden: 0/8`.
- [x] Confirm final grader reports `Missing: 0/8`.
- [x] Confirm `E01_decision.json` through `E08_decision.json` exist.
- [x] Confirm `E01_llm_prompt.json` through `E08_llm_prompt.json` exist.
- [x] Confirm `E01_llm_response.json` through `E08_llm_response.json` exist.
- [x] Confirm `GROQ_API_KEY` or API key values are not written to artifacts.
- [x] Run `python -m py_compile engine.py features.py correlation.py rca.py`.

## Tests

- [ ] Add unit tests for historical action parsing.
- [ ] Add unit tests for LLM response validation.
- [ ] Add unit tests for guardrail fallback precedence.
- [ ] Add unit tests for weak-history escalation behavior.
- [ ] Add unit tests for action param normalization.

## Documentation

- [x] Update `README.md` with setup, final engine command, all-eval command,
      and grader command.
- [x] Update `FINDINGS.md` with the LLM decision layer design.
- [x] Update `FINDINGS.md` with required reflection answers from the handout.
- [x] Record that final decision artifacts are under `artifacts/remediation/`.
- [x] Record that LLM is a final helper and not a replacement for RCA ranking.
