# Plan: Append-only audit log JSONL (P1-4)

**Status:** Verified with evidence: agent-validate.sh @ 2026-04-29T07:42:33Z (exit=0)
**Date:** 2026-04-29
**Ref commit:** `1fdb463`
**Plan location note:** Stored under `docs/plans/bootstrap-090/p1-4-audit-log-jsonl/`. Generated target repos should use `.agent/runs/<date>-<slug>/`.

## Goal

Stage an append-only `.agent/audit-log.jsonl` writer (`scripts/lib/audit_log.py` + `scripts/agent-audit-log.sh`) and wire deterministic event emission into the gate runner (`scripts/agent-eval.template.sh`), plan validator (`scripts/agent-validate-plan.sh`), and best-effort emission into the four Claude subagent prompts. Logging is on by default, silent no-op when `.agent/` is missing or the opt-out sentinel `.agent/audit-log.disabled` exists. Failures inside the writer never alter the caller's exit code. The log shape is documented in the generated `.agent/README.md`. The target repo's `.gitignore` is not modified.

## Run Artifact

`docs/plans/bootstrap-090/p1-4-audit-log-jsonl/{spec.md,plan.md}`

## Affected Areas

- `scripts/lib/audit_log.py` (NEW) — append-only writer module. Schema validation, ISO-8601 UTC timestamping, opt-out sentinel, missing-`.agent` no-op, atomic POSIX `O_APPEND` write. Public surface: `append(payload: dict, root: Path | None = None) -> int` and `main(argv)` for CLI mode.
- `scripts/agent-audit-log.sh` (NEW) — thin POSIX-bash wrapper that invokes `python3 scripts/lib/audit_log.py append --kind <k> --actor <a> [--field key=value ...]`. Always exits `0` so trap callers can preserve their own exit code.
- `scripts/agent-eval.template.sh` (MODIFIED) — capture `start_ts` and `gate`, install an `EXIT` trap that calls `scripts/agent-audit-log.sh --kind gate_run --field gate=$gate --field exit_code=$? --field duration_ms=...` so even `not_configured` (`exit 2`) is logged.
- `scripts/agent-validate-plan.sh` (MODIFIED) — wrap the `python3 ... validate_plan.py "$@"` invocation with exit-code capture **without merging streams**. Capture stdout and stderr to separate temp files (`out_file`, `err_file`), `cat "$out_file"` to stdout and `cat "$err_file" >&2` to preserve the validator's output split exactly so `--format github` consumers see byte-identical stdout. Then call `scripts/agent-audit-log.sh --kind plan_validation --field target=... --field exit_code=... [--field high=... --field medium=...] --field strict=...`. The `Summary: <h> High, <m> Medium` line is emitted by the python validator only when `--format human` (the default); the wrapper parses it from `$out_file` only when `--format` is absent or set to `human`. For `--format github`, `high`/`medium` are omitted from the audit-log payload (the audit-log schema marks them optional). Default `--format` is `human`, matching the validator default.
- `core/roles/prompts/{planner,implementer,reviewer,gate-runner}-subagent.md` (MODIFIED) — append a final "Audit log (best-effort)" bullet under `Output Format` / `Verification Expectation` instructing the subagent to invoke `bash scripts/agent-audit-log.sh --kind subagent_run --field subagent=<role> --field outcome=<status>` once the task ends.
- `core/README.md` (MODIFIED) — add `## Audit Log` section documenting the schema, opt-out sentinel, and `.gitignore` recommendation (do not auto-add).
- `scripts/bootstrap-request.sh::copy_scripts` (MODIFIED) — copy `scripts/lib/audit_log.py` and `scripts/agent-audit-log.sh` into the target.
- `scripts/lib/validate_agent_system.py` (MODIFIED) — template + generated mode existence/compile/shell-syntax checks plus content checks for `EXIT trap` invocation in `agent-eval.template.sh` and audit-log call in `agent-validate-plan.sh`.
- `scripts/lib/test_audit_log.py` (NEW) — unit tests for the writer.
- `scripts/lib/test_validate_agent_system.py` (MODIFIED) — extend existing `make_target` tests to assert audit-log scripts are copied; new test that runs `bash scripts/agent-eval.sh fast` in a fixture target and asserts a `gate_run` line lands.
- `tests/evals/audit-log-trap-fixture.sh` (NEW) — eval that bootstraps a fixture, runs `bash scripts/agent-eval.sh fast`, and parses `.agent/audit-log.jsonl` to confirm the trap fired with the correct exit code (`2` for `not_configured`).
- `scripts/agent-evals.sh` (MODIFIED) — register the new fixture under the `fast` lane.

## Owner

Implementer. Reviewer must verify (1) the caller's exit code is never altered by the writer, (2) the trap captures `not_configured`'s `exit 2`, and (3) `.gitignore` is not modified anywhere in the bootstrap flow.

## Implementation Plan

1. Author `scripts/lib/audit_log.py` with module-level constants:
   - `SCHEMA_VERSION = 1`
   - `ALLOWED_KINDS = frozenset({"gate_run", "plan_validation", "subagent_run"})`
   - `REQUIRED_PER_KIND` mapping `kind → tuple of required keys`
   - `OPT_OUT_SENTINEL = ".agent/audit-log.disabled"`
   - `LOG_PATH = ".agent/audit-log.jsonl"`
   Functions: `_now_iso()`, `_validate(payload)`, `_resolve_root(root)`, `append(payload, root=None, strict=False) -> int`, `main(argv)`. The CLI parses `--kind`, `--actor`, repeated `--field key=value` (auto-coerced to int/bool/JSON-string), `--strict`. Default `main` returns `0` even on validation failure unless `--strict` is set. Use `os.open(path, O_APPEND|O_CREAT|O_WRONLY, 0o644)` then `os.write(fd, json.dumps(payload).encode() + b"\n")` to inherit POSIX append atomicity.
2. Author `scripts/agent-audit-log.sh` with `set -u` (not `set -e`, because we must always exit 0). Resolve `python3` once, fork into the writer, ignore non-zero exit. Pass through args verbatim.
3. Modify `scripts/agent-eval.template.sh`:
   - At the top of the script, capture `audit_start_epoch_ms="$(date -u +%s)000"` (or `%s%3N` when GNU `date` is available; fall back to `%s` and append `000`).
   - Define `_audit_emit_gate_exit()` invoked by `trap '_audit_emit_gate_exit' EXIT`. The function reads `$?`, computes `duration_ms`, and calls `scripts/agent-audit-log.sh --kind gate_run --actor scripts/agent-eval.sh --field gate=$gate --field exit_code=$? --field duration_ms=...`. The trap is installed AFTER usage validation so usage errors still exit early without spurious entries.
4. Modify `scripts/agent-validate-plan.sh`:
   - Replace `exec python3 ...` with a wrapper that preserves the stdout/stderr split. Use two temp files: `out_file="$(mktemp)"`, `err_file="$(mktemp)"`. Run `python3 "$LIB_DIR/validate_plan.py" "$@" >"$out_file" 2>"$err_file"`; capture `exit_code=$?`. `cat "$out_file"` and `cat "$err_file" >&2`. Detect the format by scanning `"$@"` for `--format <value>` (default `human`). Only when the format is `human` do we attempt `grep -E '^Summary: [0-9]+ High, [0-9]+ Medium' "$out_file"` and parse `h`/`m`. Call `scripts/agent-audit-log.sh --kind plan_validation --actor scripts/agent-validate-plan.sh --field target=$target --field exit_code=$exit_code --field strict=$strict_bool` and append `--field high=$h --field medium=$m` only when both values were parsed. Remove the temp files via `trap 'rm -f "$out_file" "$err_file"' EXIT INT TERM`. Re-exit with `$exit_code`.
5. Modify the four subagent prompt files in `core/roles/prompts/`. Add under `## Output Format` (or a new `## Audit Log (best-effort)` section) one bullet:
   `Run scripts/agent-audit-log.sh --kind subagent_run --actor .agent/roles/prompts/<file>.md --field subagent=<name> --field outcome=<complete|aborted|error> after the final answer. This is best-effort; missing entries do not invalidate the run.`
6. Modify `core/README.md` to add a new `## Audit Log` section above `## Operating Model` describing the schema, opt-out sentinel, and recommendation to either commit the file (low-volume, high-signal) or add it to the local `.gitignore` manually.
7. Modify `scripts/bootstrap-request.sh::copy_scripts` to copy `scripts/lib/audit_log.py` and `scripts/agent-audit-log.sh`. No new feature flag — audit-log is unconditionally available because it is best-effort and zero-impact when `.agent/` is missing.
8. Extend `scripts/lib/validate_agent_system.py`:
   - Add module constant `AUDIT_LOG_TRAP_MARKER = "trap '_audit_emit_gate_exit' EXIT"` to detect installation in `agent-eval.template.sh`.
   - Template: assert `scripts/lib/audit_log.py` exists and compiles, `scripts/agent-audit-log.sh` exists and shell-syntaxes, `agent-eval.template.sh` contains `AUDIT_LOG_TRAP_MARKER`, `agent-validate-plan.sh` contains `agent-audit-log.sh`.
   - Generated: same shell + python existence checks against the bootstrapped paths. The trap and wrapper-call markers are identical post-copy.
9. Add `scripts/lib/test_audit_log.py` with unit tests (see Test Delta).
10. Extend `scripts/lib/test_validate_agent_system.py` with one integration test that bootstraps a target, runs `bash <target>/scripts/agent-eval.sh fast` (which exits `2` via `not_configured`), reads `.agent/audit-log.jsonl`, and asserts the line round-trips through `json.loads()` with `kind="gate_run"`, `exit_code=2`, `gate="fast"`.
11. Add `tests/evals/audit-log-trap-fixture.sh` covering the trap path including the opt-out sentinel (presence → no append).
12. Register the new eval in `scripts/agent-evals.sh` under the `fast` lane discovery.
13. Run gates listed below; convert any drift `current-code` block in this plan to `historical-code` after impl, retaining at least one stable `current-code` citation in `Existing Behaviors Preserved`.
14. Update spec/plan status to `Verified with evidence: …` once gates are green.

## Acceptance Criteria

| ID | Criterion | Verification Method | Gate |
|---|---|---|---|
| AC-1 | `scripts/agent-audit-log.sh --kind gate_run --actor scripts/agent-eval.sh --field gate=fast --field exit_code=2 --field duration_ms=10` appends one valid JSON line to `.agent/audit-log.jsonl` | `AUTOMATED-UNIT` | `python3 -m unittest scripts.lib.test_audit_log` |
| AC-2 | Missing `.agent/` directory → writer returns `0` and produces no output | `AUTOMATED-UNIT` | same |
| AC-3 | Presence of `.agent/audit-log.disabled` → writer returns `0` and does not append | `AUTOMATED-UNIT` | same |
| AC-4 | `bash scripts/agent-eval.sh fast` (default `not_configured`) produces exactly one `gate_run` line with `exit_code=2` | `AUTOMATED-UNIT` | `python3 -m unittest scripts.lib.test_validate_agent_system` |
| AC-5 | `bash scripts/agent-validate-plan.sh --force --strict <bad-plan>` (default human format) produces exactly one `plan_validation` line with `exit_code=1` and the correct `high`/`medium` counts | `AUTOMATED-INTEGRATION` | `tests/evals/audit-log-trap-fixture.sh` |
| AC-5b | `bash scripts/agent-validate-plan.sh --force --strict --format github <bad-plan>` produces exactly one `plan_validation` line with `exit_code=1`, `high` and `medium` keys absent, and the wrapper's stdout is byte-identical to a direct `python3 lib/validate_plan.py --force --strict --format github <bad-plan>` invocation | `AUTOMATED-INTEGRATION` | `python3 -m unittest scripts.lib.test_validate_agent_system` |
| AC-6 | The caller's exit code is never overwritten by the audit-log invocation (verified by injecting a writer that itself fails) | `AUTOMATED-UNIT` | `python3 -m unittest scripts.lib.test_audit_log` |
| AC-7 | Bootstrap copies `scripts/lib/audit_log.py` and `scripts/agent-audit-log.sh` into the target; `.gitignore` of the target is unchanged | `AUTOMATED-UNIT` | `python3 -m unittest scripts.lib.test_validate_agent_system` |
| AC-8 | Schema-invalid payload exits non-zero only under `--strict`; default mode exits `0` and prints `audit-log: warning:` to stderr | `AUTOMATED-UNIT` | `python3 -m unittest scripts.lib.test_audit_log` |
| AC-9 | `scripts/agent-validate.sh`, full unittests, `scripts/agent-evals.sh --fast` pass | `AUTOMATED-INTEGRATION` | listed commands |
| AC-10 | Strict plan validation passes pre-implementation | `AUTOMATED-INTEGRATION` | `scripts/agent-validate-plan.sh --force --strict docs/plans/bootstrap-090/p1-4-audit-log-jsonl` |

## Evidence

Pre-implementation grounding at `1fdb463`:

<!-- historical-code path=scripts/agent-eval.template.sh lines=1-25 ref=1fdb463 region_sha256=c07f80147d13ab29bf043e68a3447ee565d711bdd8420ea65128dfc84d39658c -->
```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

gate="${1:-fast}"

if [ "$#" -gt 1 ]; then
  printf 'Usage: %s [changed|fast|frontend|backend|shared|e2e|full|security|release]\n' "$0" >&2
  printf 'Received unsupported extra arguments: %s\n' "$*" >&2
  exit 1
fi

run() {
  printf '\n>>> %s\n' "$*"
  "$@"
}

not_configured() {
  printf 'Gate "%s" is not configured for this repository yet.\n' "$gate" >&2
  printf 'Update scripts/agent-eval.sh and .agent/gates.md after scanning the repo.\n' >&2
  exit 2
}
```
<!-- /historical-code -->

<!-- historical-code path=scripts/agent-validate-plan.sh lines=19-34 ref=1fdb463 region_sha256=93ed1294b4c28c4e9e3835385d2925b923e54abdae5aaf9a21a092db1866fdb2 -->
```bash
set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
  printf 'ERROR: python3 is required for agent-validate-plan.sh\n' >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LIB_DIR="$SCRIPT_DIR/lib"

if [ ! -f "$LIB_DIR/validate_plan.py" ]; then
  printf 'ERROR: missing %s\n' "$LIB_DIR/validate_plan.py" >&2
  exit 2
fi

exec python3 "$LIB_DIR/validate_plan.py" "$@"
```
<!-- /historical-code -->

<!-- current-code path=core/manifest.template.json lines=1-9 ref=1fdb463 region_sha256=bb93d5a1605a41ea067aec5143138c6b0da6d86e9aea2dbac235dddffa6a916e -->
```json
{
  "template_version": "{{TEMPLATE_VERSION}}",
  "instantiated_from_template_version": "{{TEMPLATE_VERSION}}",
  "instantiated_at": "{{INSTANTIATED_AT_ISO8601}}",
  "llm_tool_used": "{{LLM_TOOL_USED}}",
  "canonical_root": ".agent",
  "generated_for_repo": "{{REPO_NAME}}",
  "source_template": "{{AGENT_BOOTSTRAP_TEMPLATE_REPO_URL_OR_PATH}}",
  "features_enabled": {{FEATURES_ENABLED_JSON_ARRAY}},
```
<!-- /current-code -->

## Existing Behaviors Preserved

- `scripts/agent-eval.template.sh:1-25` — `not_configured` still exits `2` and the gate `case` dispatch is unchanged. The new EXIT trap reads `$?` from this exit, so `not_configured` runs identically; the trap only adds a side-effect (one log line) after the existing `exit 2`. Source: see `historical-code` above.
- `scripts/agent-validate-plan.sh:19-34` — exit code semantics (`0` no-High, `1` High or strict-Medium, `2` usage error) are `PRESERVED`. The wrapper captures the python exit code in `$?` and re-exits with the same value; logging is a side-effect after the validator returns. Source: see `historical-code` above.
- `core/manifest.template.json:1-9` — manifest shape is `PRESERVED`; no new field is introduced for audit-log because the writer needs no manifest-level configuration. Source: see `current-code` above.

## Verification

Pre-implementation:

```bash
scripts/agent-validate-plan.sh --force --strict docs/plans/bootstrap-090/p1-4-audit-log-jsonl
```

Post-implementation:

```bash
scripts/agent-validate.sh
python3 -m unittest scripts.lib.test_validate_plan scripts.lib.test_gate_discovery scripts.lib.test_validate_agent_system scripts.lib.test_insert_gate_candidates scripts.lib.test_audit_log
bash scripts/agent-evals.sh --fast
scripts/agent-validate-plan.sh --force --strict docs/plans/bootstrap-090/p1-4-audit-log-jsonl
```

## Required Gates

- Strict plan validation before implementation.
- Template + generated validator gates, fast evals, and the new audit-log unit tests + trap eval after implementation.

## Decision Ledger

| Decision | Chosen Behavior | Rationale | Alternatives Rejected | Caller/User Impact | Verification |
|---|---|---|---|---|---|
| Always-on with opt-out sentinel | Logging is on by default in any repo with `.agent/`; users disable by `touch .agent/audit-log.disabled` | Best-effort fallback removes a config knob and keeps observability close to the agent system | Opt-in flag (mirrors `--discover-gates` but loses the always-on observability promise); manifest field (more code, no benefit) | Repos without `.agent/` see no behavior change; repos with `.agent/` start growing a small JSONL on first gate or plan run | `test_audit_log_disabled_sentinel`, `test_audit_log_missing_agent_dir_noop` |
| Exit-code preservation | Runtime wrapper (`scripts/agent-audit-log.sh`) always returns `0`; the underlying writer (`scripts/lib/audit_log.py`) supports a `--strict` flag for tests but the wrapper never sets it | Fallback to logging silence is safer than breaking gates, especially on read-only filesystems or CI sandboxes; tests still need a way to assert schema rejection | Bubble writer errors up at runtime (would surprise gate runners with new exit codes); single-mode writer with no `--strict` (loses test coverage on validation paths) | Gate runners and plan validators retain their current exit-code contract; unit tests can still assert validation by importing the writer directly or invoking the python module with `--strict` | `test_writer_failure_does_not_alter_caller_exit`, `test_audit_log_invalid_payload_warns_default_strict_fails` |
| Stream preservation in plan-validator wrapper | Capture stdout and stderr to separate temp files (no `2>&1`); re-emit each on its original stream after the python validator returns | `--format github` consumers (CI annotation parsers) read stdout exclusively; merging stderr into stdout would break their contract. Keeping the streams split keeps the wrapper transparent | Use `2>&1 \| tee /tmp/...` (merges streams; rejected after review); pipe to `awk` (still requires merging or duplicating one stream) | Existing CI configs that consume `bash scripts/agent-validate-plan.sh --format github` see unchanged stdout byte-for-byte | `test_validate_plan_wrapper_preserves_stdout_byte_identical_under_github_format` |
| Format-aware Summary parsing | Wrapper parses `Summary: <h> High, <m> Medium` only when the request is `--format human` (default); under `--format github` it omits `high` / `medium` from the audit-log payload rather than zero-defaulting | Zero-defaulting would write false data into the log; omitting keeps the schema honest because both fields are declared optional | Always parse and silently default to zero (records false data); always require Summary parsing (breaks under `--format github`) | Audit-log readers see authoritative `high` / `medium` only when the validator actually emitted them | `test_validate_plan_audit_log_omits_counts_under_github_format` |
| Schema versioning | Embed `"v": 1` literal on every line; require all consumers to filter by `v` | Lets future schema changes coexist in the same file (mixed-version stream) without breaking existing consumers | Filename-based versioning (forces consumers to grep multiple files); no version (locks the format) | Tooling can read the log even after a schema bump; first-class compatibility | `test_audit_log_appends_schema_v1` |
| Opt-out sentinel path | `.agent/audit-log.disabled`; presence (any contents) disables writes | Simple to discover, fits inside the canonical root, no new env vars or flags | Env var `AGENT_AUDIT_DISABLE=1` (invisible to readers of `.agent/`); deletion of the log file (recreated on next write) | Users discover opt-out by reading `.agent/README.md`; works without script edits | `test_audit_log_disabled_sentinel` |
| Failure mode for malformed payload | Default exits `0` and prints `audit-log: warning: …`; `--strict` exits non-zero | Default protects callers; `--strict` lets unit tests assert validation | Always non-zero (would propagate into gate exit) or always silent (would hide schema regressions) | Tests use `--strict`; gate scripts never set it | `test_audit_log_invalid_payload_warns_default_strict_fails` |
| Empty / missing payload | Writer rejects empty input (no kind, no actor) with `audit-log: warning: …`; default returns `0` | Empty events offer no information; rejecting them avoids polluting the log with `{}` | Accept and timestamp anyway (noise) | Aborted bash trap calls without args do not corrupt the log | `test_audit_log_empty_payload_warns` |
| Subagent reliability | Subagent prompts get a best-effort logging instruction; absence is acknowledged | Claude/Codex may skip the line; enforcing via hooks is out of scope for P1-4 | Add a Claude `Stop` hook (couples to `claude-native-subagents` feature; out of scope) | Subagent runs are logged most of the time; gate and plan events are ground-truth | doc-only; covered by README review |
| Audit-log size budget | No rotation and no maximum line-count limit; records are kept small for readability and operational safety, but append correctness relies on opening the regular file with `O_APPEND` and writing each JSONL record with exactly one `os.write()` syscall, not on `PIPE_BUF` | Append-only is the smallest correct design; rotation can land later without breaking consumers because schema is versioned | Built-in size limit (would silently drop events) or rotation by date (adds new dependency and configuration) | Repos can grow `.agent/audit-log.jsonl` indefinitely; users rotate manually with `mv` if size becomes a concern | `test_concurrent_appends_atomic`, `test_audit_log_appends_schema_v1` |

## Contract Value Table

| Literal | Producer | Consumer | User-facing behavior | Test |
|---|---|---|---|---|
| `gate_run` | `scripts/agent-eval.template.sh` (EXIT trap) | `scripts/lib/audit_log.py::_validate` | Each gate invocation appends a `gate_run` line | `test_audit_log_appends_schema_v1`, eval fixture |
| `plan_validation` | `scripts/agent-validate-plan.sh` | same | Each plan validator invocation appends a `plan_validation` line | `test_audit_log_plan_validation_payload` |
| `subagent_run` | `core/roles/prompts/*-subagent.md` (best-effort) | same | Subagents append a line on completion | doc + manual review |
| `.agent/audit-log.jsonl` | writer | `agent:status` and incident reviewers | Append-only event log file | `test_audit_log_append_creates_file` |
| `.agent/audit-log.disabled` | repo owner | writer | Presence disables all writes | `test_audit_log_disabled_sentinel` |
| `audit-log: warning:` | writer | stderr | Warning prefix for malformed payloads or write errors | `test_audit_log_invalid_payload_warns_default_strict_fails` |

## Test Delta

| Action | Test | Why | Expected |
|---|---|---|---|
| ADD | `scripts/lib/test_audit_log.py::test_audit_log_appends_schema_v1` | Round-trip writer for a `gate_run` payload | one JSON line, `v=1`, `kind=gate_run`, `exit_code=2` |
| ADD | `scripts/lib/test_audit_log.py::test_audit_log_missing_agent_dir_noop` | Missing `.agent/` produces no file | exit `0`, file absent |
| ADD | `scripts/lib/test_audit_log.py::test_audit_log_disabled_sentinel` | Sentinel disables writes | exit `0`, no append, second call after sentinel removal appends |
| ADD | `scripts/lib/test_audit_log.py::test_audit_log_invalid_payload_warns_default_strict_fails` | Schema-invalid payload | default exit `0` with stderr warning; `--strict` exit `2` |
| ADD | `scripts/lib/test_audit_log.py::test_writer_failure_does_not_alter_caller_exit` | Inject permission-denied write; assert wrapper still exits `0` | shell wrapper exits `0` regardless |
| ADD | `scripts/lib/test_audit_log.py::test_concurrent_appends_atomic` | Spawn N writers; assert N well-formed lines without interleaving | line count == N, every line `json.loads()` clean |
| ADD | `scripts/lib/test_audit_log.py::test_audit_log_plan_validation_payload` | Plan-validation kind + required fields | line has `target`, `strict`, `exit_code`; `high`/`medium` present when emitted, schema accepts their absence |
| ADD | `scripts/lib/test_validate_agent_system.py::test_validate_plan_wrapper_preserves_stdout_byte_identical_under_github_format` | Wrapper does not merge streams under `--format github` | `bash scripts/agent-validate-plan.sh --format github` stdout equals `python3 ... --format github` stdout byte-for-byte |
| ADD | `scripts/lib/test_validate_agent_system.py::test_validate_plan_audit_log_omits_counts_under_github_format` | github format omits `high`/`medium` rather than zero-defaulting | audit-log line has no `high`/`medium` keys |
| ADD | `scripts/lib/test_audit_log.py::test_audit_log_empty_payload_warns` | Empty / missing args path | warning printed, no append |
| ADD | `scripts/lib/test_validate_agent_system.py::test_bootstrap_copies_audit_log_scripts` | Bootstrap stages writer | both files exist with correct mode |
| ADD | `scripts/lib/test_validate_agent_system.py::test_bootstrap_does_not_modify_target_gitignore` | Pre-create `.gitignore` in target; bootstrap; diff content | file unchanged byte-for-byte |
| ADD | `scripts/lib/test_validate_agent_system.py::test_agent_eval_trap_emits_gate_run` | Run `bash <target>/scripts/agent-eval.sh fast`; assert log appended | one `gate_run` line, `exit_code=2`, `gate="fast"` |
| ADD | `tests/evals/audit-log-trap-fixture.sh` | Eval coverage of the trap path | exit `0`, log line matches schema |
| KEEP | `scripts/lib/test_insert_gate_candidates.py`, `test_validate_plan`, `test_gate_discovery` | Unchanged | unchanged |

## Risks

- **Risk:** `EXIT` trap could double-fire if the gate script `source`s another script that also installs an `EXIT` trap. **Mitigation:** install the trap only in `agent-eval.template.sh`'s top-level scope, after the usage check, and document the requirement that gate scripts never `source` other shells.
- **Risk:** `mktemp` for `out_file`/`err_file` requires a writable temp dir; in restricted CI sandboxes this could fail. **Mitigation:** when `mktemp` fails the wrapper falls back to streaming directly via `python3 ... "$@"` (no audit-log call) and re-exits with the validator's exit code, preserving today's behavior. Audit-log is best-effort by design.
- **Risk:** Modifying `agent-validate-plan.sh` to capture both streams could alter stdout/stderr split for `--format github` consumers (e.g. CI annotation parsers). **Mitigation:** the wrapper writes to two separate files, then re-emits stdout via `cat "$out_file"` and stderr via `cat "$err_file" >&2`. No `2>&1` merge anywhere. Test asserts `--format github` stdout is byte-identical to direct python invocation.
- **Risk:** `audit-log.jsonl` grows without bound. **Mitigation:** documented as low-volume (one line per gate / plan / subagent run); rotation is explicitly out of scope and deferred to a future plan; users can `mv .agent/audit-log.jsonl .agent/audit-log.YYYY-MM.jsonl` manually.
- **Risk:** Best-effort subagent logging gives a false sense of completeness. **Mitigation:** documented in the README and Decision Ledger that subagent entries are best-effort; downstream tools must not assume one entry per delegation.
- **Risk:** Concurrent gate runs from different processes could interleave bytes. **Mitigation:** the writer opens with `O_APPEND | O_WRONLY | O_CREAT` and emits each record with exactly one `os.write()` syscall, so the kernel positions every record at the current end-of-file without interleaving. Records are sized well under 1 KB; tests cover the concurrent path with N parallel writers.
