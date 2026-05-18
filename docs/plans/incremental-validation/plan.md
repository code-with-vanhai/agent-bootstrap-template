# Stage 2 — Incremental Validation Skip

Status: Implemented in 1.1.0 (commit `341f235c`)
Owner: Maintainers (agent-bootstrap-template)
Parent proposal: [`docs/2026-05-13-gate-safety-validation-improvements-proposal.md`](../../2026-05-13-gate-safety-validation-improvements-proposal.md)

## Goal

Add a `--changed-only` flag to `scripts/agent-validate.sh` that skips
generated-mode validation when no agent-system file changed against the
selected base ref. Phase 1 is skip-only — either the full validator runs
or it is skipped entirely. The decision is driven by a Python helper
that runs `git diff --quiet -- <monitored paths>` itself, so the shell
never has to splice path lists into argv.

## Background and Current Code

`scripts/agent-validate.sh` is a thin wrapper that execs the Python
validator without parsing any flags itself:

<!-- current-code path=scripts/agent-validate.sh lines=1-17 ref=341f235ccb425acd0fd60bbefd26dbe942384119 region_sha256=b0d716c3ef2f7adcacaefaf6b4525279415da3f08c6d473a323643d25a3f185c -->
```bash
#!/usr/bin/env bash
set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
  printf 'ERROR: python3 is required for agent-validate.sh\n' >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="${AGENT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
VALIDATOR="$SCRIPT_DIR/lib/validate_agent_system.py"
CHANGED_ONLY=0

if [ "${1:-}" = "--changed-only" ]; then
  CHANGED_ONLY=1
  shift
fi
```
<!-- /current-code -->

The generated-mode validator walks a known list of agent-system files in
a single `for rel in (...)` loop and calls `validator.exists(rel)` on
each:

<!-- current-code path=scripts/lib/agent_system_validation/checks_generated.py lines=205-243 ref=341f235ccb425acd0fd60bbefd26dbe942384119 region_sha256=6d3d2a1647cf2260aaaeceb24451602e90e77abb5b52d14b43ecf1130a740663 -->
```python
    for rel in (
        ".agent/README.md",
        ".agent/manifest.json",
        ".agent/project-profile.md",
        ".agent/rulebase.md",
        ".agent/ownership.md",
        ".agent/gates.md",
        ".agent/decisions.md",
        ".agent/lessons.md",
        ".agent/roles/planner.md",
        ".agent/roles/implementer.md",
        ".agent/roles/reviewer.md",
        ".agent/roles/gate-runner.md",
        ".agent/roles/prompts/planner-subagent.md",
        ".agent/roles/prompts/implementer-subagent.md",
        ".agent/roles/prompts/reviewer-subagent.md",
        ".agent/roles/prompts/gate-runner-subagent.md",
        ".agent/workflows/bootstrap-workflow.md",
        ".agent/workflows/feature-workflow.md",
        ".agent/workflows/bugfix-workflow.md",
        ".agent/workflows/refactor-workflow.md",
        ".agent/workflows/review-workflow.md",
        ".agent/workflows/security-review-workflow.md",
        ".agent/workflows/improvement-cycle-workflow.md",
        ".agent/workflows/rule-evolution-workflow.md",
        "scripts/agent-audit-log.sh",
        "scripts/agent-eval.sh",
        "scripts/agent-gate-discover.sh",
        "scripts/agent-lock.sh",
        "scripts/agent-validate-plan.sh",
        "scripts/agent-validate.sh",
        "scripts/lib/agent_lock.py",
        "scripts/lib/audit_log.py",
        "scripts/lib/gate_discovery.py",
        "scripts/lib/gate_modes.py",
        "scripts/lib/gate_runner.py",
        "scripts/lib/validate_agent_system.py",
        "scripts/lib/secret_scan_redacted.py",
        "scripts/lib/validate_plan.py",
```
<!-- /current-code -->

`gate_modes.py` confirms generated repos can already resolve to
`DEFAULT_GATE_MODES` without an explicit `.agent/gate-modes.json`, which
sets the precedent for "Phase 1 leaves runtime alone" by introducing a
drift-tested companion list rather than refactoring the validator:

<!-- current-code path=scripts/lib/gate_modes.py lines=26-43 ref=341f235ccb425acd0fd60bbefd26dbe942384119 region_sha256=d1e06317157b25f626bc4a300b074ca25ebbe8eacce11f53f8fecdf0f7d19c9c -->
```python
DEFAULT_GATE_MODES: Tuple[str, ...] = (
    "changed",
    "fast",
    "frontend",
    "backend",
    "shared",
    "e2e",
    "full",
    "security",
    "release",
)

DEFAULT_GATE: str = "fast"
FULL_GATE: str = "full"

TEMPLATE_PATH = "core/gate-modes.json"
GENERATED_PATH = ".agent/gate-modes.json"
SUPPORTED_SCHEMA_VERSIONS = frozenset({1, 2})
```
<!-- /current-code -->

## Affected Areas

- `scripts/agent-validate.sh` (parses `--changed-only`, delegates to the
  Python helper, exits early on `0`, runs full validation on `1`, warns
  and runs full validation on `>1`).
- New file `scripts/lib/agent_system_validation/monitored_paths.py`
  (carries `MONITORED_PATHS_FOR_INCREMENTAL` and the `diff-quiet` CLI
  subcommand).
- New unit-test file `scripts/lib/test_monitored_paths.py` (drift test
  against `checks_generated.py`, exit-code mapping test).
- `core/github/agent-template-ci.example.yml` (documents
  `AGENT_VALIDATE_BASE_REF` for PR CI).
- `core/migrations/<next-version>/migration.json` (delivers updated
  `agent-validate.sh` and new `monitored_paths.py` to existing
  generated repos via `safe_overwrite`).

All affected files live in the template's bootstrap/copy pipeline; no
runtime boundary outside of the local shell + Python helper is touched.

## Implementation Plan

- Add `scripts/lib/agent_system_validation/monitored_paths.py` exposing
  a `MONITORED_PATHS_FOR_INCREMENTAL` tuple that lists every path
  `checks_generated.py` calls `validator.exists(...)` on, plus the
  adapter files the package's other check modules touch
  (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`,
  `.cursor/rules/agent-system.mdc`,
  `.github/copilot-instructions.md`,
  `.github/PULL_REQUEST_TEMPLATE.md`), plus the
  `scripts/lib/agent_system_validation/` and
  `scripts/lib/plan_validation/` package directories. The tuple is a
  drift-tested companion list: Phase 1 does not refactor the validator
  to consume it.
- The same module exposes a `diff-quiet` subcommand. Invoking
  `python3 -m scripts.lib.agent_system_validation.monitored_paths diff-quiet --root <repo> --base <ref>`
  runs `git -C <repo> diff --quiet <ref> -- <MONITORED_PATHS_FOR_INCREMENTAL>`
  and propagates git's exit code unchanged: `0` (no diff), `1` (diff
  present), or `>1` (git failed).
- Add `scripts/lib/test_monitored_paths.py` with two unit suites:
  (a) a drift test that parses `checks_generated.py` and asserts every
  string passed to `validator.exists(...)` or
  `validator.exists_either(...)` in that module is also in
  `MONITORED_PATHS_FOR_INCREMENTAL`, and (b) an exit-code suite that
  spawns the `diff-quiet` subcommand inside a `tempfile.TemporaryDirectory`
  initialized as a git repo, with one fixture per outcome (`0`, `1`,
  `>1`).
- Update `scripts/agent-validate.sh`: when the first argument is
  `--changed-only`, `shift` it, read `base_ref` from
  `${AGENT_VALIDATE_BASE_REF:-HEAD~1}`, run
  `python3 -m scripts.lib.agent_system_validation.monitored_paths diff-quiet --root "$ROOT" --base "$base_ref"`,
  capture its exit code with `set +e` / `set -e`, and branch as in the
  Decision Ledger row `incremental-skip-diff-rc`. The flag is
  generated-mode only — template-mode validation always runs in full.
- Document the new flag in `core/github/agent-template-ci.example.yml`
  with a sample PR-CI snippet that sets `AGENT_VALIDATE_BASE_REF` to
  the merge-base of the PR target branch.
- Add `scripts/lib/agent_system_validation/monitored_paths.py` to the
  template's bootstrap copy path. The existing `find` loop in
  `scripts/lib/bootstrap/copy_scripts.sh` over
  `scripts/lib/agent_system_validation/*.py` already picks the new
  file up automatically; no edit to `copy_scripts.sh` is required and
  the migration will reuse the bootstrap helper for new repos.
- Author a new migration directory
  `core/migrations/<next-version>/` whose `migration.json` lists
  `scripts/agent-validate.sh` and
  `scripts/lib/agent_system_validation/monitored_paths.py` under
  `safe_overwrite`, sets `"update_tracked_files": true`, and records a
  `notes` entry describing the new flag and the drift-test contract.

## Decision Ledger

| Decision | Chosen Behavior | Rationale | Alternatives Rejected | Caller/User Impact | Verification |
|----------|-----------------|-----------|------------------------|--------------------|--------------|
| `incremental-skip-diff-rc` (fallback shape when `diff-quiet` errors) | `0` → print "no monitored changes" and exit `0`. `1` → fall through to the existing `exec python3 validate_agent_system.py` invocation. `>1` → print a warning to stderr including the failing base ref, then fall through to the full validator. | Fails safe: any git error must lead to running full validation, never to silently skipping. Matches the gate contract that a misconfigured ref cannot suppress checks. | Treat `>1` as success (silent skip on misconfiguration); abort the shell on `>1` (regresses against the existing "always validate when in doubt" contract) | Callers that pass `--changed-only` with a bad base ref see one stderr warning line plus the existing full validator output; the script's overall exit code matches the full validator | Unit test invokes the subcommand against an empty repo with a missing ref and asserts the bash wrapper's exit code equals the full validator's exit code |
| `incremental-monitored-list-source` (single-place ownership) | `MONITORED_PATHS_FOR_INCREMENTAL` is the drift-tested companion to `checks_generated.py`. Phase 1 does not refactor the validator to consume the tuple; `test_monitored_paths.py` instead parses `checks_generated.py` and fails when the validator picks up a path the tuple does not list. | Minimizes Phase 1 blast radius. Refactoring the validator to read the tuple at runtime is deferred to a future phase that can also delete the duplicate list. | Refactor the validator to import the tuple (couples runtime code paths with the new helper; larger blast radius); keep the list shell-side (loses Python's matching semantics and tests) | Caller behavior in generated mode is unchanged — the validator still iterates its own literal tuple; the new helper only powers the shell `--changed-only` path | Drift unit test reads `checks_generated.py` and asserts the symmetric-difference between `validator.exists(...)` arguments and `MONITORED_PATHS_FOR_INCREMENTAL` is empty |
| `incremental-base-ref` (default base reference) | `${AGENT_VALIDATE_BASE_REF:-HEAD~1}`. CI workflows are expected to override with the PR merge-base. Local developers see `HEAD~1` by default, which mirrors how the shell already speaks `git diff HEAD~1` elsewhere. | Avoids needing a CI-only code path in the shell while keeping local-dev ergonomics; matches the proposal's "Phase 1 — skip-only" scope. | Hardcode `HEAD~1` (wrong in PR CI where the merge-base is not `HEAD~1`); always require an env override (breaks zero-config local use) | Local callers can run the flag without configuration; CI must set the env var or the drift-rc=1 fallback runs full validation anyway | Integration smoke test: in a temp git repo with two commits, run `--changed-only` with the default base ref and assert it exits `0`; commit a no-op change inside a monitored path and assert it falls through to full validation |

## Acceptance Criteria

| ID | Criterion | Verification Method |
|----|-----------|---------------------|
| AC-1 | When `scripts/agent-validate.sh --changed-only` runs in a generated repo with no diff between `HEAD~1` and `HEAD` inside `MONITORED_PATHS_FOR_INCREMENTAL`, the script prints the "no monitored changes" message and exits `0` without invoking `validate_agent_system.py` | AUTOMATED-INTEGRATION |
| AC-2 | When the same flag runs against a repo that changed any monitored path, the script proceeds to the existing `exec python3 validate_agent_system.py` invocation and exits with that command's exit code | AUTOMATED-INTEGRATION |
| AC-3 | When the same flag runs with an `AGENT_VALIDATE_BASE_REF` git cannot resolve, the script prints one warning line to stderr and still runs the full validator | AUTOMATED-INTEGRATION |
| AC-4 | Without `--changed-only`, `scripts/agent-validate.sh` continues to `exec python3 validate_agent_system.py "$@"` exactly as it does today | AUTOMATED-INTEGRATION |
| AC-5 | `python3 -m scripts.lib.agent_system_validation.monitored_paths diff-quiet --root <repo> --base <ref>` exits `0` on no-diff, `1` on diff inside any monitored path, and `>1` on git error | AUTOMATED-UNIT |
| AC-6 | `test_monitored_paths.py` drift test fails when a path passed to `validator.exists(...)` in `checks_generated.py` is not present in `MONITORED_PATHS_FOR_INCREMENTAL`, and passes on the current working tree | AUTOMATED-UNIT |
| AC-7 | The new migration's `safe_overwrite` list contains `scripts/agent-validate.sh` and `scripts/lib/agent_system_validation/monitored_paths.py`, and its `manifest_updates.update_tracked_files` is `true` | AUTOMATED-UNIT |

## Existing Behaviors Preserved

- `scripts/agent-validate.sh` keeps `exec`-ing `validate_agent_system.py` for every non-`--changed-only` invocation; the new branch only intercepts when the first argument equals `--changed-only` (current-code `scripts/agent-validate.sh:1-17`, lines=1-17).
- Generated-mode validation continues to walk the same path list it walks today; this stage does not edit the `for rel in (...)` block in `checks_generated.py` (current-code `scripts/lib/agent_system_validation/checks_generated.py:205-243`, lines=205-243).
- The fallback chain in `gate_modes.py` (template-mode requires `core/gate-modes.json`, generated-mode falls back to `DEFAULT_GATE_MODES`) is unchanged; this stage does not touch gate-mode loading (current-code `scripts/lib/gate_modes.py:26-43`, lines=26-43).

## Test Delta

| Test | Action | Why |
|------|--------|-----|
| `scripts/lib/test_monitored_paths.py` | ADD | New unit-test module covering the drift test against `checks_generated.py` and the `diff-quiet` subcommand exit-code map (`0`/`1`/`>1`) |
| `scripts/agent-validate.sh` integration smoke (under `tests/lib/`) | ADD | New shell smoke test that bootstraps a fixture repo, runs `--changed-only` with no diff, with a monitored diff, and with a bad base ref, and asserts each exit code matches the Decision Ledger row `incremental-skip-diff-rc` |
| `tests/migrations/<next-version>/run.sh` | ADD | Per-migration smoke that applies the new migration to a fixture repo and asserts `scripts/agent-validate.sh --changed-only` exits `0` when no agent-system file changed |
| `tests/lib/test_validate_agent_system.py` | KEEP | Existing template-mode and generated-mode unit tests must keep passing untouched; this stage does not edit the validator core |

## Risks

- Drift between `checks_generated.py` and `MONITORED_PATHS_FOR_INCREMENTAL` silently skipping validation for a newly-added agent-system file. Mitigation: ship the drift test (`test_monitored_paths.py`) in the same migration that ships the helper, and add an entry to the proposal's review checklist requiring future PRs to update both lists together.
- Misconfigured `AGENT_VALIDATE_BASE_REF` in PR CI causing the shell to fall through to full validation on every PR (no real skip). Mitigation: this is the safe failure mode by design; the Decision Ledger row `incremental-skip-diff-rc` codifies it, and the CI example in `core/github/agent-template-ci.example.yml` is updated with the recommended merge-base snippet so operators can self-correct.
- Generated repo customised `scripts/agent-validate.sh` and the migration overwrite triggers a 3-way conflict. Mitigation: rely on the existing `safe_overwrite` conflict detection; the operator must resolve the conflict and re-run `agent-sync` rather than the migration silently overwriting customisations.

## Verification

Run from the repo root:

```bash
python3 -m unittest scripts.lib.test_monitored_paths
bash scripts/agent-validate.sh --mode template
bash scripts/agent-validate.sh --changed-only       # smoke against template repo; falls through to full validation when monitored paths drifted
bash scripts/agent-evals.sh --fast
for f in tests/migrations/*/run.sh; do bash "$f"; done
```

The first command exercises the drift test and the `diff-quiet`
exit-code map. The second confirms template-mode validation is
unchanged. The third is a manual smoke against the template repo —
because the template ships its own copies of the monitored files,
`--changed-only` is expected to fall through to full validation when
any monitored path drifted in the current commit and to skip when the
working tree is clean against `HEAD~1`. The fourth runs the existing
fast gate suite. The fifth re-runs every migration smoke including the
new one introduced by this stage.

## Open Questions

- Q: Should `--changed-only` also be honoured in template mode for
  symmetry with generated mode?
  - DEFERRED: out of scope for Phase 1. The template repo is the
    source of truth for agent-system files, so running full validation
    on every template-mode invocation remains the safe default. Revisit
    in Phase 2 along with the `--files-from` flag.
- Q: What is the exact `<next-version>` slug for the migration
  directory?
  - DEFERRED: chosen at merge time by `scripts/release-prepare.sh`; the
    plan uses `<next-version>` as a placeholder.
