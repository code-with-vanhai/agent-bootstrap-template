# Agent Bootstrap Hardening Implementation Plan

Date: 2026-05-01
Status: Proposed
Audience: Maintainers implementing the next hardening sprint

## Review Decision

I agree with the proposed roadmap direction. The repo evidence supports the
main findings:

- `tests/lib/test_agent_evals_artifacts.sh` expects 4 artifact metadata files,
  while `scripts/agent-evals.sh` currently runs 5 deterministic evals.
- CI runs only 4 of the 6 `scripts/lib/test_*.py` modules and only on
  `ubuntu-latest` with Python 3.11.
- Gate modes are hardcoded in multiple consumers.
- Template version strings are repeated across bootstrap, plugin metadata,
  marketplace metadata, and the changelog.
- `scripts/bootstrap-request.sh`, `scripts/agent-sync.py`, and
  `scripts/lib/validate_agent_system.py` are too large for the modularity
  standard this repo teaches downstream users.

This plan accepts the staged order but makes three implementation corrections:

1. Stage 1 is a consistency-checked source of truth, not full code generation.
   Until a generator owns all checked-in consumers, adding a new gate mode still
   requires updating the shell/template consumers; the new validator must make
   drift fail loudly.
2. Do not create a package named `scripts/lib/validate_agent_system/` while
   keeping `scripts/lib/validate_agent_system.py`. Use a differently named
   package, such as `scripts/lib/agent_system_validation/`, and keep
   `validate_agent_system.py` as the compatibility shim.
3. The rulebase guard hook must not depend on commit messages or conversation
   context. Claude-style hooks receive tool input, not reliable VCS or chat
   state. Keep the guard conservative, off by default, and fail open on unknown
   schemas.

## Global Implementation Rules

- Keep every stage independently mergeable.
- Do not combine behavior changes with large refactors.
- Preserve downstream generated-repo compatibility unless a migration explicitly
  handles the change.
- Use stdlib-only Python for validator and CI helper scripts.
- Keep Bash compatible with macOS Bash 3.2: no associative arrays, namerefs, or
  Linux-only flags without fallback.
- Run the exit gates at the end of each stage before starting the next stage.
- Do not edit old migration fixtures unless the stage explicitly requires a new
  compatibility assertion.

## Baseline Evidence

Current repo facts to preserve in the implementation notes:

- `scripts/agent-evals.sh` deterministic evals:
  - `tests/evals/plugin-command-load.sh`
  - `tests/evals/bootstrap-render-fixture.sh`
  - `tests/evals/codex-harness-fixture.sh`
  - `tests/evals/security-gate-fixture.sh`
  - `tests/evals/audit-log-trap-fixture.sh`
- `.github/workflows/ci.yml` currently invokes:
  - `scripts.lib.test_gate_discovery`
  - `scripts.lib.test_validate_agent_system`
  - `scripts.lib.test_render_template`
  - `scripts.lib.test_validate_plan`
- Existing additional test modules:
  - `scripts.lib.test_audit_log`
  - `scripts.lib.test_insert_gate_candidates`
- Current large files:
  - `scripts/bootstrap-request.sh`: 866 lines
  - `scripts/agent-sync.py`: 1069 lines
  - `scripts/lib/validate_agent_system.py`: 852 lines
- Current version locations:
  - `scripts/bootstrap-request.sh`
  - `.claude-plugin/plugin.json`
  - `.claude-plugin/marketplace.json` metadata version
  - `.claude-plugin/marketplace.json` plugin entry version
  - top release heading in `CHANGELOG.md`

## Stage 0 - Baseline Hygiene

Estimated effort: 1 day

Goal: make the existing CI/test baseline trustworthy before feature work.

### Files To Change

- `tests/lib/test_agent_evals_artifacts.sh`
- `.github/workflows/ci.yml`
- `scripts/lib/check_test_module_coverage.py` (new)
- `scripts/lib/test_check_test_module_coverage.py` (new, if useful)

### Implementation Steps

1. Update `tests/lib/test_agent_evals_artifacts.sh` so it derives expected fast
   evals from `scripts/agent-evals.sh`.

   Requirements:

   - Parse the `deterministic_evals=( ... )` block as text.
   - Do not source `scripts/agent-evals.sh`; sourcing would execute normal
     runner setup and is too risky for a unit-style shell test.
   - Count expected evals from entries matching `tests/evals/*.sh`.
   - Assert `metadata_count == expected_count`.
   - Assert each expected eval has exactly one artifact directory containing:
     - `metadata.json`
     - `output.txt`
   - Use the same artifact-safe naming rule as the runner:
     `tr '/ ' '__' | tr -c 'A-Za-z0-9_.-' '_'`.
   - Align all metadata discovery to one strategy. Do not mix recursive `find`
     with depth-1 `glob("*/metadata.json")` unless the difference is deliberate
     and tested.

2. Add missing Python test modules to CI:

   - `python3 -m unittest scripts.lib.test_audit_log`
   - `python3 -m unittest scripts.lib.test_insert_gate_candidates`

3. Add `scripts/lib/check_test_module_coverage.py`.

   Behavior:

   - Input: path to `.github/workflows/ci.yml`.
   - Discover actual test modules from `scripts/lib/test_*.py`.
   - Ignore `__init__.py`, bytecode, and non-test helpers.
   - Parse CI text for `python3 -m unittest <module>` invocations.
   - Support both one-module-per-line and multiple modules on one line.
   - Fail with a clear message listing missing modules.
   - Use stdlib only; do not add a YAML dependency.

4. Add a CI step:

   ```yaml
   - name: All Python test modules are gated
     run: python3 scripts/lib/check_test_module_coverage.py .github/workflows/ci.yml
   ```

### Tests

Run locally:

```bash
bash tests/lib/test_agent_evals_artifacts.sh
python3 -m unittest scripts.lib.test_audit_log scripts.lib.test_insert_gate_candidates
python3 scripts/lib/check_test_module_coverage.py .github/workflows/ci.yml
bash scripts/agent-evals.sh --fast
```

### Exit Criteria

- `bash tests/lib/test_agent_evals_artifacts.sh` passes.
- CI gates all `scripts/lib/test_*.py` modules.
- Adding a sixth deterministic eval to `scripts/agent-evals.sh` causes the
  artifact test to expect six artifacts without changing the test.
- Removing a test module from the CI unittest list makes
  `check_test_module_coverage.py` fail.

### Risk

Low. This stage does not change generated repo behavior.

## Stage 1 - Gate Modes Source Of Truth

Estimated effort: 2 days

Goal: establish an authoritative gate-mode manifest and make all checked-in
consumers drift-detectable.

### Files To Change

- `core/gate-modes.json` (new)
- `scripts/lib/gate_modes.py` (new)
- `scripts/lib/validate_agent_system.py`
- `scripts/lib/insert_gate_candidates.py`
- `scripts/lib/test_gate_modes.py` or `scripts/lib/test_validate_agent_system.py`
- `scripts/bootstrap-request.sh`

### New Data File

Create `core/gate-modes.json`:

```json
{
  "schema_version": 1,
  "modes": [
    "changed",
    "fast",
    "frontend",
    "backend",
    "shared",
    "e2e",
    "full",
    "security",
    "release"
  ],
  "default_gate": "fast",
  "full_gate": "full"
}
```

### Loader Requirements

Create `scripts/lib/gate_modes.py`.

Required behavior:

- Expose `DEFAULT_GATE_MODES` as a compatibility fallback.
- Expose `load_gate_modes(root: Path, *, mode: str) -> tuple[str, ...]`.
- In template mode:
  - Require `core/gate-modes.json`.
  - Validate `schema_version == 1`.
  - Validate `modes` is a non-empty list of unique strings.
  - Validate `default_gate` and `full_gate` are included in `modes`.
- In generated mode:
  - If a future `.agent/gate-modes.json` exists, read it with the same schema.
  - Otherwise use `DEFAULT_GATE_MODES` so existing generated repos do not break.

### Validator Requirements

Update template validation to check:

- `core/gate-modes.json` exists and is valid.
- `core/manifest.schema.json` enum equals `modes`.
- `core/manifest.template.json` verification gate list equals `modes`.
- `scripts/agent-eval.template.sh` has one case branch for every mode.
- `scripts/agent-eval.template.sh` has candidate marker pairs for every mode.
- `core/commands/verify.md` documents every mode.

Important: this stage should fail on drift; it does not need to regenerate
checked-in files yet.

### Insert Candidate Changes

Update `scripts/lib/insert_gate_candidates.py` to import gate modes from
`gate_modes.py`.

Compatibility rule:

- If no gate-mode JSON exists in a generated target, use `DEFAULT_GATE_MODES`.
- Do not fail bootstrapped 0.9.0 repos just because they do not have a new gate
  modes file.

### Bootstrap Changes

Add `scripts/lib/gate_modes.py` to `copy_scripts()` so new bootstraps have the
loader available for generated validators.

Do not copy `core/gate-modes.json` into generated repos in this stage unless a
separate design explicitly chooses a generated path such as
`.agent/gate-modes.json`.

### Tests

Add tests that cover:

- Happy path: template gate modes match all consumers.
- Sad path: mutate one consumer and ensure validator fails.
- Missing `core/gate-modes.json` in template mode fails.
- Missing gate modes file in generated mode does not fail when fallback is used.
- `insert_gate_candidates.py` still returns counts for all expected modes.

Run locally:

```bash
bash scripts/agent-validate.sh --mode template
python3 -m unittest scripts.lib.test_gate_modes scripts.lib.test_insert_gate_candidates scripts.lib.test_validate_agent_system
```

### Exit Criteria

- Gate-mode drift is CI-detectable.
- Existing generated repo validation behavior remains compatible.
- A future gate-mode addition cannot silently update only one consumer.

### Risk

Low to medium. The main risk is over-tightening generated validation. Keep the
strict `core/gate-modes.json` requirement template-mode only.

## Stage 2 - CI Matrix, Version Consistency, Token Budget

Estimated effort: 2 days

Goal: broaden environment coverage and add cheap release integrity checks.

### Files To Change

- `.github/workflows/ci.yml`
- `scripts/lib/check_version_consistency.py` (new)
- `scripts/lib/test_check_version_consistency.py` (new)
- `scripts/lib/validate_agent_system.py`
- `scripts/lib/test_validate_agent_system.py`

### CI Structure

Split CI into three jobs:

1. `unit`

   Matrix:

   ```yaml
   strategy:
     fail-fast: false
     matrix:
       os: [ubuntu-latest, macos-latest]
       python: ["3.10", "3.11", "3.12"]
   runs-on: ${{ matrix.os }}
   ```

   Run:

   - shell syntax checks
   - `bash scripts/agent-validate.sh`
   - all Python unit modules
   - provider helper tests
   - eval artifact tests
   - deterministic evals
   - test module coverage check

2. `migration-fixtures`

   Keep Ubuntu-only:

   - migration fixtures use git tags and temp repos heavily
   - running them in every OS/Python cell would add cost without much signal

3. `version-consistency`

   Ubuntu-only:

   - run `python3 scripts/lib/check_version_consistency.py`

### Version Consistency Script

Create `scripts/lib/check_version_consistency.py`.

It must extract and compare:

- `template_version="..."` from `scripts/bootstrap-request.sh`
- `.claude-plugin/plugin.json` `version`
- `.claude-plugin/marketplace.json` `metadata.version`
- `.claude-plugin/marketplace.json` `plugins[].version` for
  `name == "agent-bootstrap"`
- latest release heading from `CHANGELOG.md`

Rules:

- All extracted versions must match.
- Versions must be semver without a leading `v`.
- Ignore historical migration JSON files; those intentionally contain older
  versions.
- Emit a compact report showing each source and value.

### Token Budget Validator

Add token-budget line-count checks.

Template mode paths:

- `adapters/AGENTS.md`: max 200 lines
- `adapters/CLAUDE.md`: max 200 lines
- `adapters/GEMINI.md`: max 200 lines
- `adapters/cursor-agent-system.mdc`: max 200 lines
- `adapters/copilot-instructions.md`: max 200 lines
- `core/rulebase.template.md`: max 250 lines

Generated mode paths:

- `AGENTS.md`: max 200 lines
- `CLAUDE.md`: max 200 lines
- `GEMINI.md`: max 200 lines
- `.cursor/rules/agent-system.mdc`: max 200 lines
- `.github/copilot-instructions.md`: max 200 lines
- `.agent/rulebase.md`: max 250 lines

Behavior:

- Missing optional adapters should be skipped, not failed.
- Existing file over budget should fail with line count and limit.
- The message should recommend trimming or moving scope-specific guidance into
  nested repo instructions.

### Tests

Run locally:

```bash
python3 scripts/lib/check_version_consistency.py
python3 -m unittest scripts.lib.test_check_version_consistency scripts.lib.test_validate_agent_system
bash scripts/agent-validate.sh --mode template
```

### Exit Criteria

- GitHub Actions matrix has 6 `unit` cells.
- Version skew in any one source fails CI.
- Overlong adapter/rulebase files fail validation.
- macOS cell verifies Bash 3.2-sensitive scripts enough to catch obvious
  compatibility regressions.

### Risk

Medium. macOS can expose BSD/GNU differences in `date`, `find`, `sed`, or
`mktemp`. Fix those directly; do not weaken the matrix if failures reveal real
portability assumptions.

## Stage 3 - Constitution Split

Estimated effort: 1.5 days

Goal: separate non-negotiable safety constraints from evolvable rules.

### Files To Change

- `core/constitution.template.md` (new)
- `core/rulebase.template.md`
- `core/workflows/rule-evolution-workflow.md`
- `scripts/bootstrap-request.sh`
- `scripts/lib/validate_agent_system.py`
- `scripts/lib/test_validate_agent_system.py`
- `core/hooks/pre-tool-use-rulebase-guard.py.template` (new, off by default)
- `tests/lib/test_rulebase_guard_hook.sh` (new)
- `core/hooks/README.md`
- `core/migrations/0.10.0/` (new)
- `tests/migrations/0.10.0/run.sh` (new)
- `CHANGELOG.md` and version metadata when cutting the release

### Constitution Content

Move these concepts into `core/constitution.template.md`:

- Discipline gates:
  - no completion claims without fresh evidence
  - no fixes without root cause investigation
  - no public contract change without tests/docs/consumer impact
  - no invented commands/files/functions/gates/repo facts
  - no unrelated changes bundled into a task
- Forbidden without explicit human approval:
  - production/shared deploys
  - remote database migrations
  - deleting/reordering/squashing migrations
  - editing secrets and `.env` values
  - destructive filesystem/database/infrastructure commands
  - bypassing auth/authz/validation/rate limiting/audit logging
  - weakening security controls
  - changing public API/schema/exports/persisted format without tests/docs/consumer impact
- Database/migration invariants:
  - forward migrations only
  - preserve existing data
  - rollback guidance if supported
  - never run remote migrations without approval

### Rulebase Changes

Update `core/rulebase.template.md`:

- Add a top pointer to `.agent/constitution.md`.
- Keep operational guidance, rationalization checks, scope control, correctness
  rules, contract rules, rule evolution, and lessons integration.
- Remove direct duplicate blocks that were moved to constitution, except for
  short references needed for readability.

### Bootstrap Changes

Update `copy_core_files()` to render:

- `.agent/constitution.md`
- `.agent/rulebase.md`

Update `.agent/manifest.json` canonical files if constitution should be listed.

### Validator Changes

Template mode:

- `core/constitution.template.md` exists.
- Constitution includes the non-negotiable safety headings/phrases.
- `core/rulebase.template.md` points to constitution.
- `core/workflows/rule-evolution-workflow.md` forbids editing constitution
  through rule evolution.

Generated mode:

- `.agent/constitution.md` exists.
- `.agent/rulebase.md` points to `.agent/constitution.md`.
- If `.agent/constitution.md` is missing in older generated repos, decide based
  on manifest version:
  - current/new manifests should fail
  - older manifests may skip until migration is applied

Avoid a brittle "intersection <= X lines" check unless there is a specific
utility function that ignores headings and boilerplate. Prefer direct checks:

- constitution contains required safety phrases
- rulebase contains pointer
- rulebase no longer contains the full moved block verbatim in new bootstraps

### Hook Guard

Create `core/hooks/pre-tool-use-rulebase-guard.py.template`.

Design constraints:

- Off by default.
- Must compile with stdlib Python.
- Fail open on unknown hook schema.
- Block direct writes to `.agent/constitution.md`.
- For `.agent/rulebase.md`, either:
  - emit a clear warning/permission decision when the schema supports it, or
  - allow but warn if the schema does not support reliable blocking.
- Do not rely on commit message, branch name, or conversation text.

### Migration 0.10.0

Add `core/migrations/0.10.0/`.

Migration requirements:

- Source version: `0.9.0`.
- Add `.agent/constitution.md`.
- Patch `.agent/rulebase.md` to add the constitution pointer.
- Add or update manifest sync metadata to `0.10.0`.
- Be idempotent.
- Keep existing target customizations in rulebase unless they conflict with the
  inserted pointer.

### Tests

Run locally:

```bash
bash scripts/agent-validate.sh --mode template
python3 -m unittest scripts.lib.test_validate_agent_system
bash tests/lib/test_rulebase_guard_hook.sh
bash tests/migrations/0.10.0/run.sh
```

### Exit Criteria

- New bootstrap contains both `.agent/constitution.md` and `.agent/rulebase.md`.
- Rule evolution workflow explicitly excludes constitution edits.
- Migration from 0.9.0 to 0.10.0 creates constitution and preserves rulebase
  customizations.
- Hook guard test passes and confirms fail-open behavior for unknown schemas.

### Risk

Medium. The migration touches policy files that downstream repos may customize.
Keep patching additive and test custom-rulebase fixtures.

## Stage 4 - Modularization

Estimated effort: 5 days

Goal: reduce large mixed-concern files without changing behavior.

Stage 4 must be done after Stage 0 and preferably after Stage 2, so CI has a
stronger safety net.

### Stage 4a - Validator Modularization

Estimated effort: 1 day

Do not create `scripts/lib/validate_agent_system/` because it collides
conceptually with `scripts/lib/validate_agent_system.py`.

Use:

```text
scripts/lib/agent_system_validation/
├── __init__.py
├── cli.py
├── runtime.py
├── output.py
├── checks_template.py
├── checks_generated.py
├── checks_skills.py
├── checks_adapters.py
├── checks_gates.py
├── checks_audit_log.py
├── checks_hooks.py
└── token_budget.py
```

Keep:

```text
scripts/lib/validate_agent_system.py
```

as a small compatibility shim:

```python
#!/usr/bin/env python3
from agent_system_validation.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

If package-relative imports are needed when executed as a copied generated
script, make the shim robust for both:

- template execution from repo root
- generated repo execution via `scripts/agent-validate.sh`

Bootstrap must copy the whole `agent_system_validation/` package into generated
repos.

Tests:

```bash
python3 -m unittest scripts.lib.test_validate_agent_system
bash scripts/agent-validate.sh --mode template
```

Exit criteria:

- Human, JSON, and GitHub output formats remain byte-stable enough for tests.
- Existing `scripts/agent-validate.sh` entrypoint remains unchanged.
- New generated bootstraps include the package and validate successfully.

### Stage 4b - Sync Runner Modularization

Estimated effort: 2 days

Create:

```text
scripts/lib/agent_sync/
├── __init__.py
├── cli.py
├── errors.py
├── git_ops.py
├── versions.py
├── preflight.py
├── merge.py
├── patches.py
├── codex_wrappers.py
├── manifest_ops.py
├── multi_hop.py
└── sync_log.py
```

Keep `scripts/agent-sync.py` as a compatibility shim that calls
`agent_sync.cli.main()`.

Requirements:

- Preserve exit codes.
- Preserve single-hop behavior.
- Preserve multi-hop rehearsal behavior.
- Preserve lock-file behavior.
- Preserve sync-log text format unless a test explicitly updates it.
- Preserve `scripts/agent-sync.sh` interface.

Tests:

```bash
python3 -m py_compile scripts/agent-sync.py scripts/lib/agent_sync/*.py
bash tests/migrations/0.9.0/run.sh
bash tests/migrations/multi-hop/run.sh
for f in tests/migrations/*/run.sh; do bash "$f"; done
```

Exit criteria:

- Migration fixtures are green.
- `agent-sync.sh --multi-hop` still rehearses on temp copy before touching the
  target.
- `--accept-theirs` semantics are unchanged.

### Stage 4c - Bootstrap Shell Modularization

Estimated effort: 2 days

Target structure:

```text
scripts/bootstrap-request.sh
scripts/lib/bootstrap/
├── parse_args.sh
├── detect_stack.sh
├── render_token_map.sh
├── copy_core.sh
├── copy_roles_workflows.sh
├── copy_commands.sh
├── copy_scripts.sh
├── copy_adapters.sh
├── copy_github_metadata.sh
├── copy_skills.sh
├── copy_subagents.sh
├── copy_hooks.sh
├── gate_discovery.sh
└── write_pending.sh
```

Rules:

- `scripts/bootstrap-request.sh` remains the orchestrator and public CLI.
- Source helper files with `.`.
- Keep global variable names stable unless there is a clear reason to rename.
- Do not use Bash 4-only features.
- Do not introduce process substitution if a POSIX-compatible loop is simple.
- Keep dry-run output stable where tests depend on it.

Before refactor, capture smoke output:

```bash
tmp_before="$(mktemp -d)"
bash scripts/bootstrap-request.sh --features full --harness claude --target "$tmp_before" --dry-run > /tmp/bootstrap-before.out 2>&1
```

After refactor, compare:

```bash
tmp_after="$(mktemp -d)"
bash scripts/bootstrap-request.sh --features full --harness claude --target "$tmp_after" --dry-run > /tmp/bootstrap-after.out 2>&1
diff -u /tmp/bootstrap-before.out /tmp/bootstrap-after.out
```

Tests:

```bash
bash -n scripts/bootstrap-request.sh scripts/lib/bootstrap/*.sh
bash scripts/agent-validate.sh --mode template
bash scripts/agent-evals.sh --fast
python3 -m unittest scripts.lib.test_validate_agent_system
```

Exit criteria:

- Bootstrap behavior is unchanged for minimal, standard, full, codex, and
  claude smoke targets.
- macOS CI remains green.
- No helper file exceeds roughly 200-300 lines unless it has one coherent
  responsibility.

### Stage 4 Overall Risk

Medium. Python modularization is lower risk than shell modularization. Do not
start 4c until 4a and 4b are merged and CI is green.

## Stage 5 - MCP Layer, Opt In

Estimated effort: 3-4 days

Goal: add live-tool discovery support without forcing MCP into every bootstrap.

### Files To Change

- `core/mcp/README.md` (new)
- `core/mcp/catalog.json` (new)
- `core/mcp/.mcp.json.template` (new)
- `core/skills/mcp-tool-discovery/SKILL.md` (new)
- `core/skills/manifest.json`
- `core/skills/README.md`
- `core/commands/mcp-discover.md` (new)
- `scripts/bootstrap-request.sh`
- `scripts/lib/validate_mcp_config.py` (new)
- `scripts/lib/test_validate_mcp_config.py` (new)
- `tests/evals/mcp-discovery-fixture.sh` (new)
- `README.md`
- `USAGE.md`

### Catalog

Create `core/mcp/catalog.json`:

```json
{
  "schema_version": 1,
  "servers": {
    "github": {
      "purpose": "PR, issue, and check-run context",
      "applies_when": ["github-hosted"],
      "auth_env": "GITHUB_TOKEN"
    },
    "context7": {
      "purpose": "Live documentation lookup for installed dependencies",
      "applies_when": ["package-manager-present"],
      "auth_env": null
    },
    "playwright": {
      "purpose": "Browser automation for end-to-end workflows",
      "applies_when": ["playwright-dependency-present"],
      "auth_env": null
    },
    "gitleaks-mcp": {
      "purpose": "Secret scanning support when local security gate is not configured",
      "applies_when": ["security-gate-not-configured"],
      "auth_env": null
    }
  }
}
```

The catalog is advisory. It must not imply any server is installed or trusted by
default.

### Skill

Add `core/skills/mcp-tool-discovery/SKILL.md`.

Validator constraint:

- Keep frontmatter description in the current accepted format:
  `description: Use when ...`
- Do not switch to `WHEN:` / `INVOKES:` format in this stage.

Update:

- `core/skills/manifest.json`: add `mcp-tool-discovery`
- `core/skills/README.md`: add mapping row
- README/USAGE skill-count mentions from 9 to 10 where applicable

### Command

Add `core/commands/mcp-discover.md`.

Behavior:

- Read `.agent/project-profile.md`, `.agent/gates.md`, and checked-in package
  files.
- Read `core/mcp/catalog.json` from the generated `.agent` equivalent or from
  canonical docs, depending on bootstrap design.
- Produce a report of candidate MCP servers.
- Do not write `.mcp.json` directly.
- Do not claim a server is available unless checked in or configured.

### Bootstrap Flag

Add:

```text
--with-mcp-discovery
```

Default: off.

When enabled:

- Render `.mcp.json.suggested`, not `.mcp.json`.
- Add `mcp-discovery-suggested` to `features_enabled`.
- Mention the suggested file in `.agent/bootstrap-pending.md`.

### MCP Config Validator

Create `scripts/lib/validate_mcp_config.py`.

Behavior:

- If `.mcp.json` does not exist, return success.
- If `.mcp.json.suggested` exists, lint it too.
- Parse JSON with stdlib.
- Reject obvious hardcoded credentials:
  - `sk-`
  - `ghp_`
  - `github_pat_`
  - `xoxb-`
  - `xoxp-`
  - long high-entropy literals when used as values for auth-looking keys
- Require credential references to use environment variable names, not inline
  tokens.
- Emit actionable path/key messages.

Keep the credential scanner conservative enough to avoid noisy false positives
in non-auth fields.

### Tests

Add tests for:

- catalog valid JSON and required fields
- default bootstrap does not create MCP files
- `--with-mcp-discovery` creates `.mcp.json.suggested`
- hardcoded token fixture is rejected
- env-var-based auth fixture is accepted

Run:

```bash
python3 -m unittest scripts.lib.test_validate_mcp_config
bash tests/evals/mcp-discovery-fixture.sh
bash scripts/agent-validate.sh --mode template
bash scripts/agent-evals.sh --fast
```

### Migration

Treat MCP as a later release, likely `0.11.0`, after constitution split if that
ships as `0.10.0`.

Migration should be opt-in/additive:

- Add docs/catalog files only where safe.
- Do not create active `.mcp.json` in downstream repos.
- If adding a generated suggestion file through migration, make it explicitly
  suggested and non-executable.

### Exit Criteria

- Default bootstrap behavior is unchanged.
- Opt-in bootstrap creates advisory MCP suggestion only.
- Skills count drift checks pass with 10 skills.
- MCP validator rejects obvious inline credentials.
- No network call or live MCP server invocation is required in CI.

### Risk

Low if kept opt-in. Main risk is overstating MCP availability. Use "candidate",
"suggested", and "not configured" language consistently.

## Deferred Items

These are intentionally not part of this plan:

- Skill frontmatter `WHEN:` / `INVOKES:` format.
  - Current validator requires `description: Use when`.
  - Revisit only with a validator and migration design.
- Remote marketplace source.
  - Needs a real public owner/repo/ref.
- Monorepo nested `AGENTS.md`.
  - Needs a separate nearest-instruction resolution design.
- Retrospect command and audit summary.
  - Useful, but not critical path for the current hardening sequence.
- Multi-language examples.
  - Add after core CI and modularization are stable.
- Eval flakiness `--repeat N`.
  - Behavior evals are advisory; defer until deterministic foundations are
    green.
- Python package/PyPI publishing.
  - Revisit after Stage 4 gives the helper code a packageable shape.
- Vietnamese locale layer.
  - Useful as an addon, not a core blocking item.

## Full Exit Gate Before Release

Before tagging the next release, run:

```bash
bash scripts/agent-validate.sh --mode template
python3 -m unittest scripts.lib.test_gate_discovery
python3 -m unittest scripts.lib.test_validate_agent_system
python3 -m unittest scripts.lib.test_render_template
python3 -m unittest scripts.lib.test_validate_plan
python3 -m unittest scripts.lib.test_audit_log
python3 -m unittest scripts.lib.test_insert_gate_candidates
bash tests/lib/test_llm_provider.sh
bash tests/lib/test_agent_evals_artifacts.sh
bash scripts/agent-evals.sh --fast
for f in tests/migrations/*/run.sh; do bash "$f"; done
```

If Stage 2 has landed, also require:

```bash
python3 scripts/lib/check_test_module_coverage.py .github/workflows/ci.yml
python3 scripts/lib/check_version_consistency.py
```

If Stage 3 has landed, also require:

```bash
bash tests/lib/test_rulebase_guard_hook.sh
bash tests/migrations/0.10.0/run.sh
```

If Stage 5 has landed, also require:

```bash
python3 -m unittest scripts.lib.test_validate_mcp_config
bash tests/evals/mcp-discovery-fixture.sh
```

## Recommended Branching

- `hardening/stage-0-baseline`
- `hardening/stage-1-gate-modes`
- `hardening/stage-2-ci-version-token`
- `hardening/stage-3-constitution`
- `hardening/stage-4a-validator-modules`
- `hardening/stage-4b-sync-modules`
- `hardening/stage-4c-bootstrap-modules`
- `hardening/stage-5-mcp-opt-in`

Do not merge a later stage while an earlier stage is red.

