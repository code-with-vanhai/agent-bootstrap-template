# Gate, Safety & Validation Improvements — Design Proposal

Date: 2026-05-13
Status: Implemented in 1.1.0 (2026-05-14). Each stage shipped as its own
implementation plan under `docs/plans/<slug>/plan.md`; this proposal is
preserved as the design record.
Audience: Maintainers reviewing the next improvement sprint

> **Framing note:** This is a **design proposal**, not an implementation
> plan. Plans under `docs/plans/<slug>/plan.md` are what
> `scripts/agent-validate-plan.sh` enforces section grammar on
> (Implementation Plan / Acceptance Criteria / Existing Behaviors Preserved
> / Verification). This file lives under `docs/` and exists to capture
> design decisions before any stage is scheduled. Running the plan
> validator against this file directly will flag missing sections; that is
> expected for a proposal. After review and approval, each stage becomes
> its own implementation plan under `docs/plans/<stage-slug>/plan.md`,
> conforming to the validator's section grammar and backed by evidence
> blocks.

## Summary

Four independently mergeable stages that improve safety enforcement, CI
efficiency, gate execution performance, and multi-agent coordination. Each
stage has clear exit criteria and does not depend on later stages being merged.

Ordered by priority:

1. **Stage 1 — Redacted Secret Scanner Fallback** (Task #10): safety-critical
2. **Stage 2 — Incremental Validation Skip** (Task #3): CI efficiency
3. **Stage 3 — Parallel Gate Execution Schema v2** (Task #4): gate performance
4. **Stage 4 — Agent Coordination Protocol** (Task #13): multi-agent safety

Task #5 (Cached Migration Checksums) is confirmed already implemented. The
only follow-up is a review checklist rule: migrations after `1.0.0` must
continue setting `update_tracked_files: true` when they have managed writes.

## Global Implementation Rules

- Keep every stage independently mergeable.
- Do not combine behavior changes with large refactors.
- Use stdlib-only Python (3.8+) for new scripts.
- Keep Bash compatible with macOS Bash 3.2: no associative arrays, namerefs,
  or Linux-only flags without fallback.
- Run the exit gates at the end of each stage before starting the next.
- Do not edit old migration fixtures unless the stage explicitly requires it.
- Preserve downstream generated-repo compatibility unless a migration handles
  the change.
- Every new script copied into generated repos must be added to
  `scripts/lib/bootstrap/copy_scripts.sh`, not directly to
  `scripts/bootstrap-request.sh` (which delegates).

## Baseline Evidence

Current state verified from read-only repo inspection:

- `core/gate-modes.json`: schema v1, modes list only, no parallel/composite
  support. Parser at `scripts/lib/gate_modes.py` rejects `schema_version != 1`.
- `scripts/agent-eval.template.sh`: each mode is a static `case` branch. The
  `security)` branch already integrates `gitleaks` but falls to
  `not_configured` when missing. No Python fallback exists. An EXIT trap
  always emits a `gate_run` audit event via `scripts/agent-audit-log.sh`.
- `scripts/lib/agent_system_validation/cli.py`: supports `--mode` and
  `--format` only. No `--changed-only` or `--files` flag.
- `scripts/lib/agent_system_validation/checks_generated.py`: the generated
  validator checks a much larger file set than just `.agent/` — including
  `scripts/agent-audit-log.sh`, `scripts/agent-gate-discover.sh`,
  `scripts/agent-validate-plan.sh`, `scripts/lib/audit_log.py`,
  `scripts/lib/gate_discovery.py`, `scripts/lib/plan_validation/*`, and the
  `agent_system_validation` package itself.
- `core/hooks/pre-tool-use-secret-guard.py.template`: blocks writes to
  protected paths only. Does not scan file content. Intentionally never
  reads or prints `tool_input.content`.
- `tests/evals/security-gate-fixture.sh`: expects exit 2 when `gitleaks` is
  missing. Mocks `gitleaks dir .` invocation.
- `.agent/.sync.lock`: only mechanism for concurrent protection, scoped to
  `agent-sync` runs. No runtime lock for agent task execution.
- `core/ownership.template.md`: documentation-only ownership model.
- `tracked_files` fast-path: fully implemented in
  `scripts/lib/agent_sync/merge.py` with test coverage at
  `tests/lib/test_merge_fastpath.py`.
- `scripts/lib/bootstrap/copy_scripts.sh`: authoritative location for adding
  scripts/libraries to the bootstrap copy path.

---

## Stage 1 — Redacted Secret Scanner Fallback

Estimated effort: 2 days

### Goal

Provide an automated secret scanning fallback when `gitleaks` is not
installed, using a Python scanner that **never prints matched secret values**.
Update the security gate to prefer `gitleaks --redact`, fall back to the
Python scanner, and only report `not_configured` when neither is available.

### Problem

The current security gate exits with code 2 (`not_configured`) when
`gitleaks` is absent. Most downstream repos will not have `gitleaks`
installed locally. This means the security gate provides zero value in the
common case. A grep-based fallback would leak secrets into gate output logs.

### Design Decisions

| Decision | Chosen Behavior | Rationale | Alternatives Rejected |
|---|---|---|---|
| Fallback tool | Python stdlib scanner | Available wherever Python 3.8+ is | grep (leaks values), node script (extra dep) |
| Output format | `FINDING: path:line [PATTERN_NAME]` only | Never expose matched value | Full line output (security risk) |
| gitleaks flag | `--redact` | Prevents secret values in CI logs | No flag (leaks to logs) |
| gitleaks command order | `gitleaks dir --redact .` | Flag precedes positional arg (idiomatic) | `gitleaks dir . --redact` (works but non-idiomatic) |
| `.env.*` detection | `path.name == ".env" or path.name.startswith(".env.")` | Catches `.env.production`, `.env.local` etc. `Path(".env.production").suffix` is `.production`, not `.env`, so suffix check alone misses it | Suffix-based only (misses `.env.*` files) |
| Symlink handling | Skip symlinks | Avoid following links outside repo | Follow (security risk, loops) |
| Encoding | `encoding="utf-8", errors="ignore"` | Handles binary-ish files gracefully | Strict (crashes on binary) |
| Exit behavior | exit 1 on findings, exit 0 on clean | Matches gate contract | exit 2 (conflicts with not_configured) |
| Allowlist marker | `# agent-secret-scan:allow` on same line | Lets tests/docs use literal example secrets without false positives | Per-file skip (coarse), path glob (brittle) |
| Test fixture secrets | String concatenation, not literal | Prevents scanner from flagging its own test fixtures and plan docs | Literal (scanner would flag this doc) |

### Files To Create

- `scripts/lib/secret_scan_redacted.py` — Python fallback scanner, stdlib
  only. Core responsibilities: pattern matching, redacted output, symlink
  skip, size cap, allowlist marker support.
- `scripts/lib/test_secret_scan_redacted.py` — unit tests covering:
  - Clean directory returns 0 findings.
  - File with `AKIA` pattern (built via concatenation) is detected.
  - Matched value never appears in output.
  - `.env.production` files are scanned.
  - Symlinks skipped.
  - Files over `MAX_FILE_BYTES` skipped.
  - `EXCLUDE_DIRS` entries skipped.
  - `# agent-secret-scan:allow` marker on same line suppresses finding.

### Files To Modify

- `scripts/agent-eval.template.sh` — `security)` branch: prefer
  `gitleaks dir --redact .`, fall back to Python scanner, then
  `not_configured`.
- `tests/evals/security-gate-fixture.sh` — add a third test case for the
  Python fallback path. Fake secret must be built via string concatenation
  in the fixture so the scanner does not self-detect.
- `scripts/lib/bootstrap/copy_scripts.sh` — add
  `scripts/lib/secret_scan_redacted.py` to the copy list.
- `core/skills/no-secret-leakage/SKILL.md` — reference the automated gate.
- `core/migrations/<next-version>/migration.json` — add
  `secret_scan_redacted.py` to `safe_overwrite`; update generated
  `agent-eval.sh` security case via a patch or `safe_overwrite` with
  conflict protection.

### Self-Detection Hazard

The scanner will scan `.py` and `.md` files. This document and the
`security-gate-fixture.sh` test currently would contain literal `AKIA`
strings that the scanner would flag. Mitigation:

1. In test fixtures, build fake secrets via string concatenation at runtime:
   ```bash
   fake_prefix="AKIA"
   fake_suffix="IOSFODNN7EXAMPLE1"
   echo "API_KEY = \"${fake_prefix}${fake_suffix}\"" > "$target_dir/leaked.py"
   ```
2. In docs that must mention patterns (like this proposal), append
   `<!-- agent-secret-scan:allow -->` at end of line, or use obviously
   invalid examples (e.g. `AKIA_EXAMPLE_PLACEHOLDER`). <!-- agent-secret-scan:allow -->
3. Scanner honors `# agent-secret-scan:allow` or
   `<!-- agent-secret-scan:allow -->` on the same line as the apparent match.
   This is a line-level allowlist, not a file-level exclusion.

### Migration Impact

Yes — existing generated repos need a migration to receive:

- `scripts/lib/secret_scan_redacted.py` (new file via `safe_overwrite`).
- Updated `scripts/agent-eval.sh` security case (via `safe_overwrite` with
  3-way merge, or via anchored patch on the `security)` line).

The migration must set `update_tracked_files: true` so the checksum
fast-path from Task #5 continues to apply on future syncs.

### Tests

```bash
python3 -m unittest scripts.lib.test_secret_scan_redacted
bash tests/evals/security-gate-fixture.sh
bash scripts/agent-validate.sh --mode template
bash scripts/agent-evals.sh --fast
```

### Exit Criteria

- `gitleaks` present: runs with `--redact`, gate passes/fails normally.
- `gitleaks` absent + `python3` present: Python scanner runs, never prints
  secret values, exits 1 on findings, exits 0 on clean.
- Neither available: exits 2 (`not_configured`) as before.
- Test fixture verifies redaction: output contains `[PATTERN_NAME]` but
  not the matched literal.
- `.env.production` and `.env.local` files are scanned.
- Symlinks and files over size cap are skipped.
- Allowlist marker suppresses findings on the marked line only.
- New bootstraps include `secret_scan_redacted.py` via
  `copy_scripts.sh`.
- Migration fixture confirms existing generated repos receive the new file.
- Running the scanner over this repo (including this proposal doc) reports
  zero findings.

### Risk

Low. Additive for repos that already have `gitleaks` (only gains
`--redact`). The Python scanner is conservative: false negatives are
acceptable; false positives on non-secret high-entropy strings are the
main nuisance risk. Pattern list can be tuned post-merge.

---

## Stage 2 — Incremental Validation Skip

Estimated effort: 1 day

### Goal

Add a `--changed-only` flag to `scripts/agent-validate.sh` that skips full
validation entirely when no agent-system files have changed. Phase 1 is
skip-only: either run full validation or skip completely. No partial or
selective validation in this stage.

### Problem

CI always runs full validation even when a commit only touches application
code. For large repos this adds unnecessary latency. The skip is safe
because full validation still runs on any commit that touches agent-system
files.

### Design Decisions

| Decision | Chosen Behavior | Rationale | Alternatives Rejected |
|---|---|---|---|
| Detection method | `git diff --quiet` | Atomic, no variable quoting issues, handles paths with spaces | `git diff --name-only` piped to variable (quoting bugs) |
| Base ref source | `AGENT_VALIDATE_BASE_REF` env var, default `HEAD~1` | CI sets merge-base; local dev uses HEAD~1 | Hardcoded `HEAD~1` (wrong in PR CI) |
| Error handling | On git exit >1, warn and run full validation | Fails safe — misconfigured ref still validates | Exit with git's code (decision table/code mismatch in earlier draft) |
| Scope | Generated repos only | Template repo should always run full validation | Both (template has different file set) |

### Monitored Paths

Must cover every file the generated validator inspects. From
`scripts/lib/agent_system_validation/checks_generated.py`, this includes:

- `.agent/` (all subdirectories)
- `scripts/agent-eval.sh`
- `scripts/agent-validate.sh`
- `scripts/agent-audit-log.sh`
- `scripts/agent-gate-discover.sh`
- `scripts/agent-validate-plan.sh`
- `scripts/lib/audit_log.py`
- `scripts/lib/gate_discovery.py`
- `scripts/lib/gate_modes.py`
- `scripts/lib/insert_gate_candidates.py`
- `scripts/lib/validate_agent_system.py`
- `scripts/lib/validate_plan.py`
- `scripts/lib/validate_mcp_config.py`
- `scripts/lib/secret_scan_redacted.py` (after Stage 1)
- `scripts/lib/agent_system_validation/`
- `scripts/lib/plan_validation/`
- Adapter files the validator checks: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`,
  `.cursor/rules/agent-system.mdc`, `.github/copilot-instructions.md`,
  `.github/PULL_REQUEST_TEMPLATE.md` (when present).
- Skill directories (when present): `.claude/skills/agent-bootstrap/`,
  `.agents/skills/agent-bootstrap/`.

The list lives in a new module
`scripts/lib/agent_system_validation/monitored_paths.py` as a
`MONITORED_PATHS_FOR_INCREMENTAL` tuple. This module is a **drift-tested
companion list** to `checks_generated.py`: Phase 1 does not refactor the
validator to consume the tuple. Instead, `test_monitored_paths.py` parses
`checks_generated.py` (AST or regex over `validator.exists(...)` and
`validator.exists_either(...)` call sites) and fails when a path appears
in the validator but not in the monitored list, so the two stay in sync
without coupling runtime code paths in Phase 1.

The Python module exposes a `diff-quiet` CLI subcommand so the shell never
has to splice path lists into `git diff` argv itself. The shell only reads
the exit code:

- `0`  — no monitored paths changed; the shell can skip full validation.
- `1`  — at least one monitored path changed; the shell must run full
  validation.
- `>1` — git failed (bad ref, missing repo, etc.); the shell warns and
  runs full validation (fail-safe).

### Files To Create

- `scripts/lib/agent_system_validation/monitored_paths.py` — drift-tested
  companion list for incremental scope, exposes a `diff-quiet` CLI
  subcommand that runs `git diff --quiet -- <monitored paths>` internally
  and exits with git's exit code.
- `scripts/lib/test_monitored_paths.py` — asserts every path passed to
  `validator.exists(...)` / `validator.exists_either(...)` in
  `checks_generated.py` is also present in
  `MONITORED_PATHS_FOR_INCREMENTAL` (drift test between the two).

### Files To Modify

- `scripts/agent-validate.sh` — add `--changed-only` flag. Delegate path
  expansion and the `git diff --quiet` invocation to the Python helper
  via its `diff-quiet` subcommand; the shell only reads the exit code.
- `core/github/agent-template-ci.example.yml` — document
  `AGENT_VALIDATE_BASE_REF` usage in PR CI.

### Pseudocode for `agent-validate.sh`

```bash
if [ "${1:-}" = "--changed-only" ]; then
  shift
  base_ref="${AGENT_VALIDATE_BASE_REF:-HEAD~1}"

  # Helper does the `git diff --quiet -- <monitored paths>` itself so
  # the shell never has to splice path arrays. Exit codes follow git's
  # semantics: 0 = no changes, 1 = changes, >1 = git error.
  set +e
  python3 -m scripts.lib.agent_system_validation.monitored_paths \
    diff-quiet --root "$ROOT" --base "$base_ref"
  diff_rc=$?
  set -e

  if [ "$diff_rc" -eq 0 ]; then
    printf 'No agent-system files changed (base: %s). Skipping validation.\n' "$base_ref"
    exit 0
  fi
  if [ "$diff_rc" -gt 1 ]; then
    printf 'WARN: git diff failed against base ref "%s" (exit %d). Running full validation.\n' \
      "$base_ref" "$diff_rc" >&2
    # Fall through to full validation
  fi
  # diff_rc == 1 means changes exist; fall through to full validation
fi
```

Why this shape: by keeping `git diff` invocation inside Python, the shell
is portable to macOS Bash 3.2 with no `xargs -0 -r -a` (BSD `xargs` does
not implement `-a`) and no `read -d`. It also keeps path quoting
correctness in one language.

### Files NOT Modified

- `scripts/lib/agent_system_validation/cli.py` — no Python changes for
  Phase 1.
- `scripts/lib/agent_system_validation/core.py` — no changes.
- Template-mode validation — always runs full, flag is for generated
  repos only.

### Tests

```bash
python3 -m unittest scripts.lib.test_monitored_paths
# Integration tests run in a fresh git repo with a generated .agent/
# structure; see test_monitored_paths.py for the fixture helper.
```

### Exit Criteria

- `--changed-only` with no agent file changes: prints skip message, exits 0.
- `--changed-only` with changes to any path in the monitored list: runs
  full validation.
- `--changed-only` with bad base ref: warns and runs full validation (does
  not silently skip).
- Without `--changed-only`: unchanged behavior (backward compatible).
- Template repo validation unaffected.
- Drift test: adding a new `validator.exists(...)` call in
  `checks_generated.py` without updating `monitored_paths.py` fails
  `test_monitored_paths.py`.

### Migration Impact

Yes — existing generated repos need a migration because both the updated
`scripts/agent-validate.sh` (handling the new `--changed-only` flag) and
the new `scripts/lib/agent_system_validation/monitored_paths.py` helper
must reach them. Repos that never pass `--changed-only` see no behavior
change, but the files still have to be delivered via `safe_overwrite` so
they can opt in later without re-running bootstrap.

The migration must set `"update_tracked_files": true` so the checksum
fast-path from Task #5 continues to apply on future syncs.

### Risk

Low. Worst case: a misconfigured `AGENT_VALIDATE_BASE_REF` causes full
validation to run (safe fallback). The flag cannot cause validation to be
skipped when it should run, because any git error falls through to full
validation. Biggest risk is path drift between `checks_generated.py` and
`monitored_paths.py`; the drift test mitigates this.

### Phase 2 (Deferred)

- `--files-from <path>` for selective per-file validation.
- Dependency graph: changes to `gates.md` trigger `agent-eval.sh`
  validation subset.
- Check groups: validate only the subset relevant to changed files.

---

## Stage 3 — Parallel Gate Execution (Schema v2)

Estimated effort: 5-6 days

### Goal

Design and implement `gate-modes.json` schema v2 with `composite_gates`
support, enabling parallel execution of independent gate modes within a
composite gate like `full`. Preserve full backward compatibility with
schema v1.

### Problem

When a repo configures `full` gate to run frontend, backend, shared, and
e2e checks sequentially, total gate time is the sum of all sub-gates.
Independent sub-gates (frontend, backend) can run in parallel, reducing
wall-clock time by 40-50% for repos with separated concerns.

### Design Decisions

| Decision | Chosen Behavior | Rationale | Alternatives Rejected |
|---|---|---|---|
| Schema versioning | v2 additive, v1 still accepted | Backward compat for all existing repos | Breaking change (migration burden) |
| Composite definition | `composite_gates` map referencing existing modes | Only valid modes can be composed | Inline sub-commands (bypasses mode validation) |
| Parallel semantics | Run all jobs in group, wait all, aggregate | Simpler, predictable | `fail_fast: true` (kill + cleanup, MVP complexity) |
| Log capture | Per-process temp file, cat on completion | Prevents interleaved output | Shared stdout (unreadable) |
| Child audit suppression | Set `AGENT_EVAL_SUPPRESS_AUDIT=1` for sub-gate child invocations; emit one composite `gate_run` event from the runner | Matches plan's "one gate_run per composite" contract without forking the EXIT trap | Accept N events (breaks audit consumers expecting composite-level event) |
| Exit code aggregation | Worst non-2 wins; but composite exits 2 when **all** sub-gates returned 2 | Avoids composite passing when nothing ran | "2 is always skipped" (full could pass with zero real work) |
| Cycle detection | Validate at load: no self-reference, no composite-to-composite | Prevents infinite recursion | Runtime detection (too late) |
| Composite gate detection | `gate_runner.py is-composite --gate ... --gate-modes ...` CLI | Avoids brittle inline `python3 -c` string interpolation | Inline `python3 -c` (shell quoting hazards) |
| MVP scope | No `fail_fast`, no dependency DAG between stages | Reduce complexity for first iteration | Full DAG scheduler (over-engineered) |

### Schema v2 Specification

```json
{
  "schema_version": 2,
  "modes": [
    "changed", "fast", "frontend", "backend", "shared", "e2e",
    "full", "security", "release"
  ],
  "default_gate": "fast",
  "full_gate": "full",
  "composite_gates": {
    "full": {
      "stages": [
        {"parallel": ["frontend", "backend", "shared"]},
        {"serial": ["e2e"]}
      ]
    }
  }
}
```

Rules:

- `composite_gates` is optional. If absent, schema v2 behaves like v1.
- Each key in `composite_gates` must be a member of `modes`.
- Each mode referenced in `stages[].parallel[]` or `stages[].serial[]`
  must be a member of `modes`.
- A composite must not reference itself (direct cycle).
- A composite must not reference another composite (no nesting in v2;
  revisit in v3 if needed).
- Stages execute in order: all jobs in stage N complete before stage N+1.
- Within `parallel`, listed modes run concurrently.
- Within `serial`, modes run sequentially in listed order.
- If all sub-gates return exit 2 (`not_configured`), composite returns 2.
- If any sub-gate returns non-zero (other than 2) and at least one
  sub-gate was actually configured, composite returns the worst non-2
  exit code after all stages complete.
- If all configured sub-gates pass (exit 0) and any remaining return 2,
  composite returns 0.

### Audit Contract

The current `agent-eval.sh` EXIT trap always emits a `gate_run` event
referencing the active gate name. For composite execution this would
cause N+1 events (one per sub-gate + one for the composite itself),
breaking downstream consumers expecting one event per user-invoked gate.

Resolution: the composite runner sets `AGENT_EVAL_SUPPRESS_AUDIT=1` in
the environment of each child `agent-eval.sh` invocation. The
`_audit_emit_gate_exit` trap checks this variable and returns early when
set. The runner then emits exactly one composite `gate_run` event
containing:

- `gate`: composite name (e.g., `full`)
- `exit_code`: aggregated exit code
- `duration_ms`: wall-clock total
- `sub_gates`: JSON array of `{gate, exit_code, duration_ms}` per sub-gate

`scripts/lib/audit_log.py` and `scripts/agent-audit-log.sh` must accept
the optional `sub_gates` field; schema version stays at `v: 1`
(additive field).

### Files To Create

- `scripts/lib/gate_runner.py` — composite execution logic. Exposes:
  - `load_composite(gate_name, gate_modes_path) -> CompositeGate | None`
  - `run_composite(composite, eval_script_path, root) -> int`
  - `run_stage(stage, eval_script_path, root) -> list[SubGateResult]`
  - `aggregate_exit_codes(results) -> int`
  - CLI: `python3 gate_runner.py is-composite --gate X --gate-modes Y`
    prints `yes` or `no` to stdout.
  - CLI: `python3 gate_runner.py run --gate X --gate-modes Y --eval-script Z --root R`
    executes the composite.
- `scripts/lib/test_gate_runner.py` — unit tests:
  - All sub-gates passing → composite exit 0.
  - One sub-gate failing (exit 1) → composite exit 1.
  - All sub-gates exit 2 → composite exit 2.
  - Mix of pass + exit 2 → composite exit 0.
  - Mix of fail + exit 2 → composite exits with failure code.
  - Parallel stage runs concurrently (timing or mock assertion).
  - Serial stage runs sequentially.
  - Cycle detection rejects self-reference.
  - Cycle detection rejects composite-to-composite.
  - Missing composite → returns None.
  - `is-composite` CLI prints correct answer for composite and
    non-composite gates.
  - Child invocations receive `AGENT_EVAL_SUPPRESS_AUDIT=1`.
  - Runner emits exactly one audit event with `sub_gates` array.

### Files To Modify

- `scripts/lib/gate_modes.py` — accept `schema_version: 2`. Validate
  `composite_gates` structure, mode references, and cycle rules.
- `scripts/lib/test_gate_modes.py` — add v2 tests. Keep all v1 tests
  green.
- `scripts/agent-eval.template.sh`:
  - Add composite detection via `gate_runner.py is-composite` CLI
    (not inline `python3 -c`).
  - `exec python3 scripts/lib/gate_runner.py run ...` when composite.
  - In `_audit_emit_gate_exit`: check
    `[ "${AGENT_EVAL_SUPPRESS_AUDIT:-0}" = "1" ]` and return early.
- `scripts/lib/audit_log.py` — accept optional `sub_gates` field in
  `gate_run` events (JSON array, each entry with `gate`, `exit_code`,
  `duration_ms`).
- `scripts/agent-audit-log.sh` — pass through optional `--field
  sub_gates_json=...` entries correctly.
- `core/gate-modes.json` — update to `schema_version: 2` (no composites
  defined initially; repos opt in per-repo).
- `scripts/lib/bootstrap/copy_scripts.sh` — add `scripts/lib/gate_runner.py`
  to the copy list so generated repos receive the runner.

### Migration Impact

Yes — existing generated repos need a migration to receive:

- `scripts/lib/gate_runner.py` (new file via `safe_overwrite`).
- Updated `scripts/agent-eval.sh` with composite detection and audit
  suppression logic (via `safe_overwrite` or anchored patch).
- Updated `scripts/agent-audit-log.sh` and `scripts/lib/audit_log.py`
  (via `safe_overwrite`).
- Updated `scripts/lib/gate_modes.py` (accepts `schema_version: 2`).

The migration must set `update_tracked_files: true`. If generated repos
already customized `agent-eval.sh`, conflict detection triggers and user
must explicitly accept updates.

**Not migrated in this stage:** `.agent/gate-modes.json` is **not**
generated, copied, or rewritten by this migration. Generated repos that
want to define composite gates opt in by creating
`.agent/gate-modes.json` themselves, mirroring the v2 schema documented
in `core/gate-modes.json`. Repos that never create the file continue to
use the upstream `core/gate-modes.json` defaults via the existing
`gate_modes.py` lookup; the runner falls back to `DEFAULT_GATE_MODES`
when no `composite_gates` entry exists for the requested gate.

### Tests

```bash
python3 -m unittest scripts.lib.test_gate_modes
python3 -m unittest scripts.lib.test_gate_runner
bash scripts/agent-validate.sh --mode template
bash scripts/agent-evals.sh --fast
bash tests/evals/security-gate-fixture.sh
```

### Exit Criteria

- Schema v1 files continue to work unchanged.
- Schema v2 without `composite_gates` behaves identically to v1.
- Schema v2 with `composite_gates` runs sub-gates per stage config.
- Cycle detection prevents self-reference and composite nesting.
- All-exit-2 composite returns 2 (no silent pass when nothing ran).
- Child sub-gate invocations do not emit audit events (suppressed).
- Runner emits exactly one composite `gate_run` event with `sub_gates`.
- Per-sub-gate logs captured separately, printed sequentially.
- Existing `security-gate-fixture.sh` test passes unchanged.
- Template validation passes with updated `core/gate-modes.json`.
- Migration fixture confirms generated repos receive `gate_runner.py`
  and audit changes.

### Risk

Medium. Main risks:

- Process management in Bash/Python: signal handling and cleanup on
  SIGINT/SIGTERM. Use `try/finally` with subprocess group cleanup.
- Audit contract change: downstream consumers must handle the optional
  `sub_gates` field. Schema stays at v1 (additive).
- Migration conflicts: if a repo already customized `agent-eval.sh`,
  the user must resolve conflicts. Clear messaging required.

### Future Work (Not In This Stage)

- `fail_fast: true` — kill remaining parallel jobs on first failure.
- Dependency ordering between stages (DAG).
- Composite nesting (composite referencing another composite).
- Generated `.agent/gate-modes.json` with composite definitions during
  bootstrap (currently repos opt in by editing the file post-bootstrap).
- Visual progress output for parallel stages.

---

## Stage 4 — Agent Coordination Protocol

Estimated effort: 6-8 days (design doc + MVP + tests)

### Goal

Provide a file-level advisory locking mechanism for multi-agent scenarios
within the same working tree. Reduce (not eliminate) merge conflicts when
multiple agents work on the same repository concurrently.

### Problem

When 2+ agents work on the same repo (same working tree, same machine),
there is no mechanism to prevent them from editing overlapping files
simultaneously. `ownership.md` is documentation-only. The only existing
lock is `.agent/.sync.lock`, which protects `agent-sync` runs only.

### Scope & Non-Goals

**In scope (MVP):**

- Advisory file-path locking within a single working tree on a single
  machine.
- Atomic lock acquisition via `O_CREAT|O_EXCL` (same pattern as sync lock).
- TTL-based expiration with configurable timeout.
- Glob-pattern path ownership with overlap detection.
- CLI wrapper for acquire/release/list/prune/run.
- `trap EXIT` cleanup in the wrapper for crash safety.
- Integration guidance for workflows (documentation, not enforcement).

**Not in scope:**

- Cross-machine or cross-clone coordination.
- Cross-worktree coordination (different git worktrees).
- Remote branch conflict prevention.
- Guaranteed zero merge conflicts (impossible with local-only locks).
- Automatic enforcement in workflows (advisory in MVP).

### Design Decisions

| Decision | Chosen Behavior | Rationale | Alternatives Rejected |
|---|---|---|---|
| Lock storage | `.agent/locks/*.lock.json` | Colocated with agent system | `/tmp` (lost on reboot) |
| Lock gitignore | `.agent/locks/` in `.gitignore` | Locks are ephemeral | Committed locks (stale in history) |
| Atomicity | `O_CREAT\|O_EXCL` on lock file | Race-free on local filesystem | `fcntl.flock` (not portable) |
| TTL | Default 60 min, configurable via `--ttl-minutes` | Prevents permanent stale locks | No TTL (manual cleanup needed) |
| Cleanup | `trap EXIT` in wrapper + `prune` for stale + TTL | Handles normal exit, signals, crashes | Manual only (locks accumulate) |
| Path matching | `fnmatch` glob patterns | Matches `ownership.md` convention | Regex (overkill) |
| Overlap detection | Bidirectional: fnmatch + common prefix | Catches containment (`src/**` vs `src/auth/login.ts`) | One-directional (misses containment) |
| CLI primary mode | `agent-lock.sh run --paths '...' -- <command>` | Lock held for command duration, auto-released via trap | Separate acquire/release only (easy to forget release) |
| CLI secondary mode | `agent-lock.sh acquire` + `release --session-id` | Long-running sessions need manual control; caller owns the lifecycle | Only `run` mode (too restrictive) |
| Session ID | Random UUID v4 at acquire time | Unique, no collision | PID (reuse after process death) |
| Python entrypoint | `agent_lock.py` with `argparse main()` | CLI wrapper needs a real Python CLI, not just a library class | Library only (shell can't invoke) |

### Lock File Format

```json
{
  "v": 1,
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "paths": ["src/auth/**", "src/middleware/auth.ts"],
  "acquired_at": "2026-05-13T10:00:00Z",
  "ttl_minutes": 60,
  "task": "Fix auth token refresh bug",
  "pid": 12345
}
```

Fields: schema version, session UUID, glob patterns claimed, UTC
timestamp, TTL, human description, owning PID.

Lock file naming: `.agent/locks/<session_id>.lock.json`.

### CLI Contract (`scripts/agent-lock.sh`)

```
agent-lock.sh run --paths '<glob>[,<glob>...]' [--task '<desc>'] \
                  [--ttl-minutes N] -- <command...>
    Acquire a lock, run <command>, release on exit (EXIT/INT/TERM/HUP).

agent-lock.sh acquire --paths '<glob>[,<glob>...]' [--task '<desc>'] \
                      [--ttl-minutes N]
    Acquire a lock, print session_id to stdout, exit.
    Caller is responsible for calling release.

agent-lock.sh release --session-id <uuid>
    Release a lock by session_id.

agent-lock.sh list [--include-expired] [--json]
    List active locks (human or JSON output).

agent-lock.sh prune [--stale-minutes N]
    Remove expired locks. Default: TTL-based expiration.
```

The `run` subcommand is the recommended usage — lifecycle is bounded by
the wrapped command. The `acquire`/`release` pair exists for workflows
that span multiple shell invocations; callers must implement their own
cleanup (session-level `trap` in the outer script that manages the
workflow).

### Python Module Contract

`scripts/lib/agent_lock.py` must expose:

- `AgentLockManager` class (library API) with `acquire`, `release`,
  `list_locks`, `prune`, `check_overlap`.
- `main(argv)` function for argparse-based CLI.
- Subcommands: `acquire`, `release`, `list`, `prune`, `check-overlap`.
- `run` subcommand is shell-side only (trap handling in bash). Python
  does not reimplement shell lifecycle.

Running the module:

```bash
python3 scripts/lib/agent_lock.py acquire \
  --paths 'src/auth/**' --task 'test' --ttl-minutes 60 --root .
# stdout: session_id

python3 scripts/lib/agent_lock.py release \
  --session-id <uuid> --root .
# exit 0 if released, exit 1 if not found

python3 scripts/lib/agent_lock.py list --root . [--json]

python3 scripts/lib/agent_lock.py prune --root . [--stale-minutes 120]
```

### Overlap Detection

```
def _paths_overlap(paths_a, paths_b) -> bool:
    # Bidirectional fnmatch + common prefix heuristic.
    for a in paths_a:
        for b in paths_b:
            if fnmatch.fnmatch(b, a) or fnmatch.fnmatch(a, b):
                return True
            a_base = a.split("*")[0].rstrip("/")
            b_base = b.split("*")[0].rstrip("/")
            if a_base and b_base:
                if a_base.startswith(b_base) or b_base.startswith(a_base):
                    return True
    return False
```

Trade-off: this is intentionally over-protective. Advisory locks
benefit from false positives (prevent overlap) more than they hurt from
false negatives. Unit tests cover the common cases:

- `src/auth/**` conflicts with `src/auth/login.ts` ✓
- `src/**` conflicts with `src/auth/**` ✓
- `src/api/**` does NOT conflict with `src/auth/**` ✓
- `**/*.ts` conflicts with `src/auth/login.ts` ✓

### Files To Create

- `scripts/lib/agent_lock.py` — library + argparse `main()`.
- `scripts/lib/test_agent_lock.py` — unit tests:
  - Acquire succeeds on empty lock dir.
  - Acquire fails with `LockConflictError` on overlap.
  - Release removes lock; unknown session_id returns False.
  - Expired locks ignored during overlap check.
  - `prune` removes expired, preserves active.
  - Overlap cases listed above all pass.
  - Atomic acquire under concurrent threads (threading test).
  - CLI: `acquire` prints session_id on stdout.
  - CLI: `release` with non-existent UUID exits non-zero.
  - CLI: `list --json` emits valid JSON array.
- `scripts/agent-lock.sh` — bash wrapper with `run`/`acquire`/`release`/
  `list`/`prune` subcommands. `run` uses `trap cleanup EXIT INT TERM HUP`
  to call `release` unconditionally.

### Files To Modify

- `.gitignore` — add `.agent/locks/`.
- `scripts/lib/bootstrap/copy_scripts.sh` — add `agent_lock.py` and
  `agent-lock.sh` to copy list.
- `core/workflows/feature-workflow.md` — add advisory step about locks
  for multi-agent scenarios.
- `core/workflows/bugfix-workflow.md` — same advisory step.
- `core/README.md` — new "Multi-Agent Coordination (Optional)" section.

### Migration Impact

Yes — existing generated repos need a migration to receive:

- `scripts/lib/agent_lock.py` (new).
- `scripts/agent-lock.sh` (new).
- `.gitignore` patch to add `.agent/locks/` (anchored, idempotent).
  Use anchor like `^# Agent coordination` or prepend with `skip_if_contains`.
- Updated workflow files (`feature-workflow.md`, `bugfix-workflow.md`)
  via `safe_overwrite` with 3-way merge protection.
- Updated `.agent/README.md` via `safe_overwrite`.

The migration must set `update_tracked_files: true`.

### Tests

```bash
python3 -m unittest scripts.lib.test_agent_lock
bash -n scripts/agent-lock.sh

# Integration tests (in a temp dir)
scripts/agent-lock.sh acquire --paths 'src/test/**' --task 'test'
# captures session_id
scripts/agent-lock.sh list
scripts/agent-lock.sh release --session-id "$session_id"
scripts/agent-lock.sh list  # empty

# Run mode with auto-cleanup
scripts/agent-lock.sh run --paths 'src/test/**' -- echo "done"
# lock dir empty after

# Overlap detection
scripts/agent-lock.sh acquire --paths 'src/auth/**' --task 'a'
scripts/agent-lock.sh acquire --paths 'src/auth/login.ts' --task 'b'
# second call exits non-zero

bash scripts/agent-validate.sh --mode template
bash scripts/agent-evals.sh --fast
```

### Exit Criteria

- `acquire` creates atomic lock file with correct schema.
- `release` removes lock file; `run` auto-releases on exit/signal/error.
- Overlap detection catches containment and exact-match cases.
- Non-overlapping paths do not conflict.
- Expired locks ignored during overlap check.
- `prune` removes only expired locks.
- `.agent/locks/` is gitignored.
- Python `main()` exposes argparse CLI with all required subcommands.
- Workflow docs mention locks as optional/advisory.
- No existing tests break.
- Migration fixture confirms existing generated repos receive new files.

### Risk

Medium-High. Main risks:

- False overlap detection: glob-vs-glob comparison is imprecise. The
  common-prefix heuristic may over-lock. Acceptable for advisory locks.
- Stale locks from killed processes: `trap EXIT` handles most cases,
  but `kill -9` leaves stale locks. `prune` and TTL mitigate.
- Adoption friction: advisory locks work only if workflows use them.
  MVP is tooling + docs; enforcement is future work.
- Path normalization: Windows paths, trailing slashes, relative vs
  absolute. MVP normalizes to POSIX relative paths from repo root.

### Future Work (Not In This Stage)

- Automatic lock acquisition in workflows (enforcement).
- Cross-worktree coordination via shared lock directory.
- Lock visualization in agent status output.
- Integration with `ownership.md` for automatic path inference.
- Lock contention metrics in audit log.
- Timeout/retry with backoff when lock is held.

---

## Dependency Map

```
Stage 1 (Secret Scanner)     ← independent; can merge first
Stage 2 (Incremental Skip)   ← independent of Stage 1; needs Stage 1's
                              copy_scripts.sh updated scope if merged later
Stage 3 (Parallel Gates)     ← touches agent-eval.sh; should land after Stage 1
                              to avoid merge conflict
Stage 4 (Agent Coordination) ← independent of Stages 1-3
```

Stages 1 and 4 can be developed in parallel. Stage 2 and Stage 3 both
touch script scope or `agent-eval.sh` — sequence them to minimize
conflicts.

## Recommended Branching

- `improvement/stage-1-secret-scanner-fallback`
- `improvement/stage-2-incremental-validation`
- `improvement/stage-3-parallel-gates-v2`
- `improvement/stage-4-agent-coordination`

## Migration Impact Summary

All four stages require a migration to propagate behavior to existing
generated repos. Earlier drafts of this proposal incorrectly listed
Stages 2-4 as needing no migration; that was wrong because generated
repos ship their own copies of the scripts, and new files or changed
behavior must be delivered via `safe_overwrite` entries.

| Stage | Migration Required? | Key Entries |
|-------|--------------------|----|
| Stage 1 | Yes | `safe_overwrite`: `scripts/lib/secret_scan_redacted.py` (new), `scripts/agent-eval.sh` (security case) |
| Stage 2 | Yes | `safe_overwrite`: `scripts/agent-validate.sh` (updated flag), `scripts/lib/agent_system_validation/monitored_paths.py` (new) |
| Stage 3 | Yes | `safe_overwrite`: `scripts/lib/gate_runner.py` (new), `scripts/agent-eval.sh`, `scripts/agent-audit-log.sh`, `scripts/lib/audit_log.py`, `scripts/lib/gate_modes.py`. `.agent/gate-modes.json` is **not** auto-created; repos opt in by writing their own file. |
| Stage 4 | Yes | `safe_overwrite`: `scripts/lib/agent_lock.py` (new), `scripts/agent-lock.sh` (new); `patches`: `.gitignore` anchored insert; `safe_overwrite`: workflow files |

Every migration added by these stages must set
`"update_tracked_files": true` in `migration.json` to preserve the
checksum fast-path from Task #5.

## Bootstrap Impact Summary

All new files copied into generated repos must be added to
`scripts/lib/bootstrap/copy_scripts.sh`, not to
`scripts/bootstrap-request.sh` directly. The bootstrap script delegates
to the modular `copy_scripts.sh` helper.

| Stage | New entries in `copy_scripts.sh` |
|-------|---|
| Stage 1 | `scripts/lib/secret_scan_redacted.py` |
| Stage 2 | `scripts/lib/agent_system_validation/monitored_paths.py` (picked up automatically by the existing `find` loop over the `agent_system_validation` package) |
| Stage 3 | `scripts/lib/gate_runner.py` |
| Stage 4 | `scripts/lib/agent_lock.py`, `scripts/agent-lock.sh` |

## Full Exit Gate Before Release

After all stages are merged:

```bash
# Existing gates
bash scripts/agent-validate.sh --mode template
python3 -m unittest scripts.lib.test_gate_discovery
python3 -m unittest scripts.lib.test_validate_agent_system
python3 -m unittest scripts.lib.test_render_template
python3 -m unittest scripts.lib.test_validate_plan
python3 -m unittest scripts.lib.test_audit_log
python3 -m unittest scripts.lib.test_insert_gate_candidates
python3 -m unittest scripts.lib.test_gate_modes
bash tests/lib/test_llm_provider.sh
bash tests/lib/test_agent_evals_artifacts.sh
bash scripts/agent-evals.sh --fast
for f in tests/migrations/*/run.sh; do bash "$f"; done

# New gates from this proposal
python3 -m unittest scripts.lib.test_secret_scan_redacted
python3 -m unittest scripts.lib.test_monitored_paths
python3 -m unittest scripts.lib.test_gate_runner
python3 -m unittest scripts.lib.test_agent_lock
bash tests/evals/security-gate-fixture.sh
```

## Review Checklist for Future Migrations

After this proposal is implemented, all future migrations that include
managed file writes must:

- [ ] Set `"update_tracked_files": true` in `migration.json`
      (preserves checksum fast-path from Task #5 implementation).
- [ ] Include `scripts/lib/secret_scan_redacted.py` in `safe_overwrite`
      when updating generated scripts (after Stage 1 merges).
- [ ] Verify `security-gate-fixture.sh` still passes after migration
      apply.
- [ ] If adding new scripts, update
      `scripts/lib/agent_system_validation/monitored_paths.py` so the
      incremental skip keeps covering them (after Stage 2 merges).

## Next Steps After Approval

Each stage in this proposal maps to a validator-conformant
implementation plan under:

```
docs/plans/<stage-slug>/plan.md
```

with the required sections (`Implementation Plan`, `Acceptance Criteria`,
`Existing Behaviors Preserved`, `Verification`) populated with
evidence-block citations per the planner role contract.

Proposed slugs:

- `docs/plans/secret-scanner-fallback/plan.md` (Stage 1)
- `docs/plans/incremental-validation/plan.md` (Stage 2)
- `docs/plans/parallel-gates-v2/plan.md` (Stage 3)
- `docs/plans/agent-coordination/plan.md` (Stage 4)

This proposal stays as the approved reference for design decisions and
cross-stage concerns.

## Deferred Items

These are intentionally not part of this proposal:

- **Dependency graph validation** (Phase 2 of Task #3): selective
  per-file validation based on which agent files changed. Revisit after
  Phase 1 skip-only is stable.
- **`fail_fast` for parallel gates**: killing child processes on first
  failure. Revisit after MVP parallel execution is proven stable.
- **Composite gate nesting**: composite referencing another composite.
  Revisit if real use cases emerge.
- **Cross-worktree lock coordination**: shared lock directory for git
  worktrees. Revisit after single-worktree MVP is adopted.
- **Automatic lock enforcement in workflows**: making lock acquisition
  mandatory rather than advisory. Revisit after advisory adoption shows
  value.
- **Secret pattern tuning**: expanding or refining the regex pattern
  list based on real-world data. Ongoing maintenance after Stage 1
  ships.
- **Rollback support for migrations** (original Task #12): reverse
  migration path. Deferred to schema v2 design.
