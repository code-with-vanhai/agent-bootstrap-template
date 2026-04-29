# Spec: Append-only audit log JSONL (P1-4)

**Status:** Verified with evidence: agent-validate.sh @ 2026-04-29T07:42:33Z (exit=0)
**Date:** 2026-04-29
**Ref commit:** `1fdb463`
**Plan location note:** Stored under `docs/plans/bootstrap-090/p1-4-audit-log-jsonl/` because this template repo dogfoods plans there. Generated target repos should use `.agent/runs/<date>-<slug>/`.
**Track:** 0.9.0 P1-4, after P0-1–P0-4 + P1-1 landed on `main`.

## Problem

Bootstrapped repos already produce useful artifacts during agent work — `scripts/agent-eval.sh` runs gates with non-zero exit codes, `scripts/agent-validate-plan.sh` reports finding counts and exit codes, and Claude subagents finish each turn — but none of these produce a durable, append-only record. There is no machine-readable timeline an agent or human can grep to answer:

- "Which gate ran last? With what exit code?"
- "How often does the security gate fail in this repo?"
- "Did the planner subagent finish its last delegation?"

This is a missing observability primitive. P1-4 adds an append-only `.agent/audit-log.jsonl` that captures gate runs and plan validations deterministically (via shell traps) and subagent runs best-effort (via subagent prompt instructions). The log is ground truth for `agent:status` features, telemetry exports, and incident review without introducing daemons, network calls, or new dependencies.

## Goals

- Add `scripts/lib/audit_log.py` and `scripts/agent-audit-log.sh` providing `append(payload)` semantics that write one JSON object per line to `<root>/.agent/audit-log.jsonl`. Best-effort: a missing `.agent/` directory or write failure must not break the caller.
- Wire deterministic `kind=gate_run` events into `scripts/agent-eval.template.sh` via an `EXIT` trap so even `not_configured` (exit 2) and gate failures are captured.
- Wire deterministic `kind=plan_validation` events into `scripts/agent-validate-plan.sh` capturing the python validator's exit code and the strict flag.
- Wire best-effort `kind=subagent_run` instructions into the four `core/roles/prompts/*-subagent.md` files asking the subagent to call `scripts/agent-audit-log.sh` after finishing its task.
- Provide an opt-out sentinel (`.agent/audit-log.disabled`) that disables all audit-log writes without removing the writer scripts.
- Document the log shape, opt-out path, and `.gitignore` recommendations in `core/README.md` (the generated `.agent/README.md`). **Do not** modify the target repo's `.gitignore`.
- Cover the writer with unit tests (schema validation, append, missing-dir, opt-out sentinel) and the eval-trap with a shell fixture in `tests/evals/`.

## Non-Goals

- No log rotation, compaction, retention, redaction, or shipping — append-only file on local disk only.
- No new harness, no new skill, no new gate mode, no change to `EXPECTED_GATE_MODES`.
- No modification of the target repo `.gitignore`. The log is staged at `.agent/audit-log.jsonl` and users decide whether to commit or ignore it locally.
- No automatic mining of the log file beyond what tests assert. Future `agent:status` work consumes this log; that is P1-5+ territory.
- No subagent-level enforcement. Subagent prompts include a final logging step but Claude/Codex may skip it; this is acknowledged in the docs as best-effort.

## Event Schema (v=1)

Every event is a single-line JSON object terminated by `\n`. Required keys:

| Key | Type | Description |
|---|---|---|
| `v` | integer | Schema version. Always `1` in this release. |
| `ts` | string | UTC timestamp `YYYY-MM-DDTHH:MM:SSZ` (no fractional seconds). |
| `kind` | string | One of `gate_run`, `plan_validation`, `subagent_run`. |
| `actor` | string | Repo-relative POSIX path of the script or prompt that emitted the event. |

Per-kind required keys:

- `gate_run`: `gate` (string), `exit_code` (integer), `duration_ms` (integer).
- `plan_validation`: `target` (string), `exit_code` (integer), `strict` (boolean). Optional: `high` (integer), `medium` (integer); both are emitted only when the wrapper successfully parses the `Summary: <h> High, <m> Medium` line from a `--format human` run. Under `--format github` (no `Summary:` line) both are omitted rather than zero-defaulted to avoid recording false data.
- `subagent_run`: `subagent` (string), `outcome` (one of `complete`, `aborted`, `error`).

Optional keys: `notes` (string), `extra` (object). The writer rejects unknown top-level keys to keep the schema crisp; future versions will bump `v`.

## Failure-mode Contract

- Missing `.agent/` directory → writer is a silent no-op (returns 0).
- Existing `.agent/audit-log.disabled` → writer is a silent no-op (returns 0).
- Write error (e.g. read-only filesystem) → writer prints a single warning to stderr (`audit-log: warning: ...`) and exits 0 so the caller's exit code is preserved.
- Malformed payload (missing required keys, bad type) → the underlying writer (`scripts/lib/audit_log.py`) exits non-zero **only when invoked with `--strict`** (used by unit tests). The runtime shell wrapper (`scripts/agent-audit-log.sh`) never sets `--strict` and always exits `0`, so gate and plan-validator scripts cannot have their exit code altered by a schema regression.
- Concurrent writers → file is opened with `O_APPEND | O_WRONLY | O_CREAT` and each event is emitted via a single `os.write(fd, line_bytes)` syscall. The kernel positions the write at the current end-of-file under `O_APPEND`; concurrent writes do not interleave when the writer issues exactly one syscall per record. (`PIPE_BUF` is the analogous guarantee for pipes/FIFOs and is not the source of correctness for regular files.)

## Opt-out

Creating `.agent/audit-log.disabled` (any contents) disables all writes. The file is documented in `core/README.md`. Removing it re-enables logging on the next event.

## Validation Expectations

- Template-mode validator asserts the existence and `py_compile` of `scripts/lib/audit_log.py`, the existence and shell-syntax of `scripts/agent-audit-log.sh`, and the presence of an `audit-log` invocation in both `scripts/agent-eval.template.sh` (as part of an `EXIT` trap) and `scripts/agent-validate-plan.sh`. Validator also asserts that `agent-validate-plan.sh` does **not** contain `2>&1` to enforce the stream-preservation contract.
- Generated-mode validator asserts the same scripts exist in the target.
- `scripts/lib/test_audit_log.py` covers schema validation, append, missing-dir no-op, opt-out sentinel, and concurrent-append correctness.
- `tests/evals/audit-log-trap-fixture.sh` runs `agent-eval.sh` against a temp repo and asserts exactly one `gate_run` line is appended with the expected `exit_code`.
- `scripts/agent-validate.sh`, full unittests, `scripts/agent-evals.sh --fast`, and strict plan validation pass post-implementation.
