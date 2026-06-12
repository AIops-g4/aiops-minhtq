# AGENTS.md

Guidance for AI agents working on this AIOps remediation lab.

## Environment

Project type: local Python CLI for an evidence-driven AIOps remediation engine.
Conda environment: `machine_learning`
Path: `D:\Asus\App\miniconda\workspace\envs\machine_learning`

```powershell
conda activate machine_learning
```

If Conda activation is unavailable:

```powershell
D:\Asus\App\miniconda\workspace\envs\machine_learning\python.exe --version
```

```powershell
cd data-pack
```

Run one incident from `data-pack`:

```powershell
python engine.py decide --incident eval/E01.json --history incidents_history.json --actions actions.yaml
```

Run all eval incidents from `data-pack`:

```powershell
1..8 | ForEach-Object {
  $id = "E{0:D2}" -f $_
  python engine.py decide --incident "eval/$id.json" --history incidents_history.json --actions actions.yaml
}
```

Grade output:

```powershell
python grade.py --audit audit.jsonl --expected eval/expected.json
```

## Read First

Before implementing:

1. `data-pack/HANDOUT.md`
2. `data-pack/README.md`
3. `specs/README.md`
4. `specs/system-context.md`
5. `specs/data-model.md`
6. Relevant change folder under `changes/`
7. Existing implementation files in `data-pack/`, if present

Do not infer requirements from code alone.

## Project Boundaries

- Preserve the CLI contract in `data-pack/HANDOUT.md`.
- Preserve the `audit.jsonl` grading contract.
- Keep stable architecture and data knowledge in `specs/`.
- Keep feature-specific implementation plans in `changes/`.
- Prefer modifying existing modules before creating new files.
- Avoid new abstractions unless they remove real complexity.
- Do not add dependencies unless the change clearly requires them.

## Domain Rules

- Build decisions from logs, traces, metrics, topology, historical outcomes, and action metadata.
- Use logs and traces as first-class evidence; metrics alone are not enough.
- Treat `trigger_alert.service` as an investigation starting point, not the root cause.
- Do not hard-code direct `root_cause_class -> action` rules.
- Use `page_oncall` only for novel or unsafe-to-auto-act cases, not because it has zero direct cost.
- Always write auditable evidence to `audit.jsonl`.
- Do not name uncertain outputs as final truth.

## Data Modeling

- Use type hints for public functions and public data structures.
- Use `dataclass` or Pydantic models for structured incident, evidence, action, and decision data.
- Parse historical `actions_taken` into the schema from `actions.yaml`.
- Normalize live raw logs into templates before comparing with historical `log_signatures`.
- Split metric keys into `service` and `metric`.
- Keep raw debug values such as counts, z-scores, and ratios in `details`, not in normalized top-level scores.

## Naming Rules

Follow Python PEP 8 naming conventions:

- Modules and files: `snake_case.py`
- Packages/directories: `snake_case`
- Functions, methods, and variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Classes and dataclasses: `PascalCase`
- Private helpers: prefix with `_`
- Test files: `test_<module_name>.py`
- Test functions: `test_<expected_behavior>`

Use domain-specific names:

- `incident` for the current incident input.
- `evidence` for logs, metrics, traces, topology, or history signals.
- `candidate_action` for an action being considered.
- `decision` for the final remediation choice.
- `confidence` for model or rule certainty.
- `risk_score` for estimated action risk.
- `audit_record` for one JSONL audit entry.
- `root_cause_candidate` for a possible cause.

Avoid vague names such as `data`, `result`, `item`, `obj`, `tmp`, and `stuff` unless the scope is tiny and obvious.

## Clean Code Rules

- Keep functions focused on one responsibility.
- Prefer pure functions for parsing, scoring, ranking, and decision logic.
- Separate business logic from CLI parsing.
- Separate decision logic from file loading and serialization.
- Avoid hidden side effects except for explicit IO functions.
- Prefer early returns over deeply nested conditionals.
- Keep public functions small and typed.
- Do not introduce global mutable state.
- Do not duplicate scoring or filtering logic across files.
- Use explicit error messages when input files are missing or malformed.

## Python Quality

- Follow PEP 8 formatting.
- Prefer `pathlib.Path` over raw string path manipulation.
- Prefer `logging` over `print` for internal diagnostics.
- Use `json`, `yaml`, and file IO through small dedicated helper functions.
- Avoid broad `except Exception` unless re-raising or logging with context.
- Do not silently swallow errors.

## Checks

Before completing code changes, run available checks:

```powershell
python -m black .
python -m ruff check .
python -m mypy .
```

If these tools are not installed, do not add them automatically unless requested; report which checks could not be run.
