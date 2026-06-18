# AGENTS.md

Guidance for AI agents working on the Week 3 individual lab:
Closed-Loop Auto-Remediation.

## Environment

Project type: local Python orchestrator plus Bash runbooks for an AIOps
closed-loop remediation lab.

Lab root:

```powershell
cd w3/individual-lab/lab-closed-loop
```

The lab pack runs on Docker Compose and local Python through `uv`.

```powershell
cd data-pack
bash scripts/start_stack.sh
```

Stop and reset the stack:

```powershell
cd data-pack
bash scripts/stop_stack.sh
```

Required Python packages for the learner implementation:

```powershell
uv pip install requests pyyaml prometheus_client
```

The orchestrator is expected to run from the learner submission directory:

```powershell
uv run python closed_loop.py --config config.yaml
```

## Read First

Before implementing:

1. `data-pack/HANDOUT.md`
2. `data-pack/README.md`
3. `specs/README.md`
4. `specs/system-context.md`
5. `specs/runtime-contracts.md`
6. `specs/observability-data.md`
7. Relevant change folder under `changes/`
8. Existing implementation files in the learner submission root, if present

Do not infer requirements from the sample solution alone. The handout and specs
are the source of truth.

## Submission Boundary

In the handout, `your-name/` means the learner submission directory. In this
repo, treat `w3/individual-lab/lab-closed-loop/` as that working submission root
unless the user explicitly creates a separate named folder.

Expected learner-owned files at the submission root:

```text
closed_loop.py
config.yaml
runbooks/restart_service.sh
runbooks/scale_replicas.sh
runbooks/clear_cache.sh
DESIGN.md
SUBMIT.md
```

`data-pack/` is provided lab material. Avoid editing it unless the user asks for
lab-pack maintenance. Learner code should read from it, run its scripts, or copy
the required ideas into learner-owned files.

## Project Boundaries

- Preserve the contracts in `data-pack/HANDOUT.md`.
- Keep stable architecture and data knowledge in `specs/`.
- Keep feature-specific implementation plans in `changes/`.
- Prefer a rule-based decision engine unless the user explicitly requests LLM
  integration.
- Do not add cloud dependencies. The lab must run locally.
- Do not require Grafana for grading. Grafana is for debugging only.
- Do not hard-code thresholds that belong in `config.yaml` or
  `data-pack/data/baseline.json`.
- Do not execute a real runbook before a successful dry-run.
- Do not run two remediation actions concurrently for the same service.

## Domain Rules

- The closed-loop sequence is Detect, Decide, Dry-run, Act, Verify, Rollback or
  Halt.
- Every action must pass all safety checkpoints before execution: dry-run,
  blast-radius, verify plan, rollback path, and circuit-breaker state.
- Alertmanager and Prometheus use short service labels such as `payment-svc`.
- Docker containers use prefixed names such as `ronki-payment-svc`.
- Runbooks should accept short service names and map them to Docker container
  names internally.
- Decision validation must reject runbooks outside the configured registry
  before spawning any subprocess.
- A validation failure is not an action failure and must not increment the
  circuit-breaker counter.
- Verify must query Prometheus and require multiple successful samples, not just
  a successful shell command.
- Circuit breaker reset is manual by default.

## Naming Rules

Follow Python PEP 8 naming conventions:

- Modules and files: `snake_case.py`
- Packages/directories: `snake_case`
- Functions, methods, and variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Classes and dataclasses: `PascalCase`
- Private helpers: prefix with `_`

Use domain-specific names:

- `alert` for the Alertmanager alert payload.
- `service` for the short service label, for example `checkout-svc`.
- `container_name` for the Docker container name, for example
  `ronki-checkout-svc`.
- `runbook` for the script selected by the decision engine.
- `rollback_runbook` for the rollback script.
- `audit_event` for one structured JSON log event.
- `verify_sample` for one Prometheus verification result.

Avoid vague names such as `data`, `result`, `item`, `obj`, and `tmp` unless the
scope is tiny and obvious.

## Clean Code Rules

- Separate alert polling, decision, safety checks, runbook execution, verify,
  rollback, and logging.
- Use `pathlib.Path` for file paths.
- Use small helpers for loading YAML and JSON.
- Use `requests` with explicit timeouts for Alertmanager and Prometheus calls.
- Use `subprocess.run` with an explicit timeout for runbooks.
- Prefer structured return values over string parsing when possible.
- Avoid broad `except Exception` unless logging context and returning a safe
  refusal.
- Keep JSON log events machine-readable and one event per line.
- Make orchestrator-level `--dry-run` disable all real runbook execution.

## Checks

Minimum local checks before submission:

```powershell
uv run python closed_loop.py --help
bash runbooks/restart_service.sh --service payment-svc --dry-run
bash runbooks/clear_cache.sh --service payment-svc --dry-run
bash runbooks/scale_replicas.sh --service payment-svc --dry-run
```

Acceptance checks are the chaos scenarios in `data-pack/HANDOUT.md` and
`data-pack/data/expected.json`. Paste representative orchestrator logs into
`SUBMIT.md`.
