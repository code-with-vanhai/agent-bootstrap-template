# PR-3 Plan: 0.5.0 release ship — version bump + docs + no-op migration + 0.5.0 migration test + CHANGELOG

**Status:** Draft
**Date:** 2026-04-28
**Parent proposal:** `docs/2026-04-27-llm-provider-abstraction-proposal.md` (revision 3.1, approved)
**Plan location note:** `docs/plans/llm-provider/pr-3/plan.md` (same rationale as PR-1/PR-2: `scripts/agent-validate.sh:244` treats `.agent/` existence as "downstream repo" mode).
**Scope:** Final PR of the 0.5.0 LLM provider abstraction series. Ships the version bump, documentation, no-op migration manifest, 0.5.0 migration regression test, and the cumulative CHANGELOG entry. No new runtime behavior beyond what PR-1 and PR-2 already landed.
**Ref commit:** `2ee1d15`

---

## Goal

Make 0.5.0 a **shippable release**: every surface that names a version, every user-facing doc that mentions Claude-only eval workflow, every migration tooling input that downstream `agent-sync.sh --to 0.5.0` will read, and the changelog. **No code logic changes.** The runtime work landed in PR-1 (`619bd2d`) and PR-2 (`e347eec`). PR-3 is the release-engineering wrapper.

The 0.5.0 migration is intentionally **no-op for existing 0.4.0 repos**: PR-1 and PR-2 added new files in the template tree (`scripts/lib/llm_provider.sh`, `tests/evals/codex-harness-fixture.sh`, `tests/evals/mocks/*`, etc.) but did not modify any file that downstream repos materialize into `.agent/`. Existing repos synced to 0.4.0 do not need any patch beyond the manifest update plus the standard sync-log audit entry.

Important migration boundary: `agent-sync.py` has no migration walker. It loads only the requested target migration, so `core/migrations/0.5.0/migration.json` intentionally accepts `from_versions: ["0.4.0"]` only. Repos currently at `0.3.0` or `0.3.2` must sync to `0.4.0` first, then sync to `0.5.0`; a single-step `0.3.x -> 0.5.0` sync is rejected by design in PR-3.

---

## Context (Grounding)

### Version constants before PR-3 pin to 0.4.0

At ref `2ee1d15`, the release version surfaces still pin to `0.4.0`:

```bash
template_version="0.4.0"
```

```json
  "version": "0.4.0",
```

```json
    "version": "0.4.0"
```

The marketplace file pins the version twice (top-level metadata + per-plugin); both must bump. The same 8-char snippet `"version": "0.4.0"` appears at both line 8 and line 15 of `marketplace.json` (region_sha256 identical because content identical).

### Existing migration manifest schema (template for the 0.5.0 no-op)

<!-- current-code path=core/migrations/0.4.0/migration.json lines=1-5 ref=2ee1d15 region_sha256=e5d62387012af550cf7e0f010e76ab44dfee4507447eb7b96120d3f771812585 -->
```json
{
  "schema_version": 1,
  "version": "0.4.0",
  "from_versions": ["0.3.0", "0.3.2"],
  "to": "0.4.0",
```
<!-- /current-code -->

The 0.5.0 manifest uses the same schema with `from_versions: ["0.4.0"]`, `to: "0.5.0"`, empty `safe_overwrite` and empty `patches` arrays (no-op), and `manifest_updates.replace` flipping `template_version` and `synced_to_template_version` to `0.5.0`. `replace_from_git_tag.synced_to_template_commit` resolves the v0.5.0 tag at apply time. Because the runner loads only the requested target migration, this manifest does not accept `0.3.x` sources.

### README's Claude-only eval framing

At ref `2ee1d15`, README still frames evals as Claude-only:

```
Run optional headless behavior evals from this repo when the Claude CLI is available and the cost/flakiness tradeoff is acceptable:
```

```
The eval runner exits 0 with `SKIP` when the Claude CLI is missing. Evals are intentionally not wired into validation or CI by default.
```

These two non-fence lines establish the Claude-only framing of `README.md` §"Validation And Evals". The intermediate `\`\`\`bash ... \`\`\`` block at lines 243-246 is omitted from the evidence snippet because nested triple-backtick fences make the plan harder to read. PR-3 rewrites the prose to reference both providers (`--provider claude|codex`), tightens the example commands, links to the new authoritative `tests/evals/README.md`, and documents `AGENT_LLM_PROVIDER` / `CODEX_BIN` env vars at the level of detail appropriate for the top-level README.

### tests/evals/README.md is Claude-only and stale

At ref `2ee1d15`, `tests/evals/README.md` still describes the runner and eval list in Claude-only terms:

```markdown
- `agent-validate.sh` checks files, placeholders, syntax, and required content.
- `agent-evals.sh` invokes `claude -p` and may consume model tokens.
```

```
- `plugin-command-load.sh`: verifies Claude loads plugin commands from the canonical `core/commands/` custom path.
- `verify-before-claim.sh`: rejects completion claims without fresh verification evidence.
- `root-cause-first.sh`: starts bugfix work with root-cause investigation.
- `no-invented-gates.sh`: refuses to invent conventional test commands when gates are not configured.
```

```markdown
2. Source `tests/evals/test-helpers.sh`.
3. Use `create_test_project` for a temporary repo with minimal `.agent/` files.
4. Use `run_claude` to execute the prompt.
5. Assert both required behavior and forbidden behavior.
6. Add the script to `scripts/agent-evals.sh`.
```

The `tests/evals/README.md` is also stale on the eval set: `verify-before-claim` / `root-cause-first` / `no-invented-gates` are listed under "Fast evals" but were demoted to `--behavior` in 0.4.0; `plan-grounding.sh` (added 0.4.0) and `codex-harness-fixture.sh` (added 0.5.0 PR-2) are missing entirely; and the "Adding Evals" recipe still says `run_claude` instead of the provider-agnostic `run_llm` introduced in PR-1.

PR-3 rewrites this file to be the authoritative provider matrix per the parent proposal §"User-Facing Configuration".

---

## Plan

### 1. Version bumps (3 surfaces)

- `scripts/bootstrap-request.sh`: `template_version="0.4.0"` → `"0.5.0"`.
- `.claude-plugin/plugin.json`: `"version": "0.4.0"` → `"0.5.0"`.
- `.claude-plugin/marketplace.json`: both `metadata.version` and `plugins[0].version` → `"0.5.0"`.

No other surface ships a literal version string. Fixtures under `tests/migrations/0.3.0/after/.agent/manifest.json` and `tests/migrations/0.4.0/run.sh` are deliberately pinned to their respective baseline versions and must NOT be bumped.

### 2. New file: `core/migrations/0.5.0/migration.json`

Schema-1 manifest, no-op:

```json
{
  "schema_version": 1,
  "version": "0.5.0",
  "from_versions": ["0.4.0"],
  "to": "0.5.0",
  "safe_overwrite": [],
  "patches": [],
  "manifest_updates": {
    "replace": {
      "template_version": "0.5.0",
      "synced_to_template_version": "0.5.0"
    },
    "replace_from_git_tag": {
      "synced_to_template_commit": "0.5.0"
    },
    "append_to_array_unique": {
      "notes": "Synced to agent-bootstrap-template v0.5.0: LLM provider abstraction (Claude + Codex switchable). New env vars AGENT_LLM_PROVIDER, CODEX_BIN, CODEX_EXTRA_ARGS. Provider-portable evals migrated to run_llm; plugin-command-load.sh stays Claude-Code-specific. No downstream content files modified by this migration."
    },
    "merge_array_unique": {}
  }
}
```

The empty `safe_overwrite` and `patches` arrays are the no-op contract. Downstream repos receive only the manifest update plus the standard sync-log audit entry that `agent-sync.py:702 append_sync_log` always emits on a successful apply. Rationale: PR-1/PR-2 changed `scripts/lib/`, `tests/`, and proposal docs in the **template tree**; none of those paths are materialized into downstream `.agent/` by `bootstrap-request.sh`.

**Upgrade path constraint.** `from_versions` is intentionally `["0.4.0"]` only — not cumulative. `agent-sync.py` is single-step (no migration walker): `agent-sync.py:614` selects `migrations[-1]` and `agent-sync.py:155-194 load_migration` enforces `current ∈ accepted_sources`. Repos still on 0.3.0 / 0.3.2 MUST run `agent-sync.sh --to 0.4.0` before `agent-sync.sh --to 0.5.0`; the single-step `0.3.x → 0.5.0` path is rejected by design with a clear `migration metadata mismatch` error. The accompanying `core/migrations/0.5.0/README.md` (see §5) documents this explicitly. Cumulative `from_versions: ["0.3.0", "0.3.2", "0.4.0"]` was rejected because it would require duplicating every patch + safe_overwrite entry from `core/migrations/0.4.0/migration.json` into the 0.5.0 manifest, breaking the no-op framing and creating a high-risk drift surface for future patches.

### 3. New file: `tests/migrations/0.5.0/run.sh`

Modeled on `tests/migrations/0.4.0/run.sh` post-fix (commit `2ee1d15`). Coverage:

- `clean-from-0.4.0`: source manifest at `0.4.0`, no customizations. Asserts manifest bump, idempotent re-apply, and that NO downstream files outside `.agent/manifest.json` and `.agent/sync-log.md` change (no-op contract).
- No customized-* scenarios because there are no patches for customization to interact with. A single clean-from + idempotency cycle is sufficient evidence the no-op manifest applies cleanly.

The test creates an ephemeral local `v0.5.0` tag at HEAD if missing (deleted on EXIT), same pattern as `tests/migrations/0.4.0/run.sh:70-72`. The 0.4.0 fixture for migration setup is sourced from `tests/migrations/0.3.0/after/` then synced to 0.4.0 via `agent-sync.sh --to 0.4.0` (genuine 0.4.0 state, NOT a manifest-only lie — this avoids the trap that the previous `clean-from-0.3.2` case fell into; see commit `2ee1d15` body).

**Commit between syncs.** After the setup sync to 0.4.0 produces the fixture's 0.4.0 state, the test commits the fixture worktree (`git add .` then `git -c user.email=t@t -c user.name=Test commit -m "fixture@0.4.0"`) before invoking `--to 0.5.0`. `agent-sync.py:648-649` rejects dirty worktrees without `--allow-dirty`; the test follows the same `commit-between-syncs` pattern used in the idempotency leg of `tests/migrations/0.4.0/run.sh:142-146`.

### 4. CHANGELOG entry (cumulative for 0.5.0)

Single `## 0.5.0 - <date>` section summarizing PR-1 + PR-2 + PR-3:

- Provider abstraction: `scripts/lib/llm_provider.sh` registry + `run_llm` / `skip_if_llm_unavailable`.
- Codex routing: `--provider codex` CLI flag, `AGENT_LLM_PROVIDER` env, conservative codex quota regex, `--sandbox workspace-write` default, `CODEX_BIN` / `CODEX_EXTRA_ARGS` env.
- Migrated 6 provider-portable evals off Claude-specific helpers (back-compat shims pinned to claude retained).
- New deterministic eval: `tests/evals/codex-harness-fixture.sh` (filesystem-only, runs in `--fast`).
- Checked-in mocks: `tests/evals/mocks/{claude-quota,claude-misaligned,codex-quota,codex-auth}.sh`.
- Path-normalization in `scripts/agent-evals.sh` for relative `CLAUDE_BIN` / `CODEX_BIN`.
- Pre-existing 0.4.0 migration test fix (commit `2ee1d15`): dropped invalid `clean-from-0.3.2` fixture; v0.3.2 ephemeral-tag fallback now pins the real commit `499eb163`.
- No-op migration: existing 0.4.0 repos receive only a manifest update plus the sync-log audit entry.
- **Upgrade-path note (important):** the 0.5.0 migration accepts `from_versions: ["0.4.0"]` only. Repos still on 0.3.0 or 0.3.2 must run `agent-sync.sh --to 0.4.0` before `agent-sync.sh --to 0.5.0`. Single-step `0.3.x → 0.5.0` is rejected by `agent-sync.py` (no migration walker exists by design).
- Verification status footer mirroring 0.4.0 style: deterministic gates green, behavior evals advisory.

### 5. Documentation updates

- `tests/evals/README.md`: full rewrite to be the authoritative provider matrix (per parent proposal §"User-Facing Configuration"). Includes:
  - Provider precedence: `--provider` > `AGENT_LLM_PROVIDER` env > default `claude`.
  - Per-provider env vars: `CLAUDE_BIN`, `CLAUDE_EXTRA_ARGS`, `CODEX_BIN`, `CODEX_EXTRA_ARGS`.
  - Codex invocation contract: `codex exec --skip-git-repo-check --color never --sandbox workspace-write [CODEX_EXTRA_ARGS] <prompt>`. Override via `CODEX_EXTRA_ARGS="--sandbox read-only"` if needed.
  - Eval matrix updated to current state: deterministic (`plugin-command-load`, `codex-harness-fixture`), behavior (4 LLM-driven), integration (2 LLM-driven). `plugin-command-load.sh` SKIPs cleanly when `provider != claude`.
  - "Adding Evals" recipe uses `run_llm` (not `run_claude`).
- `README.md` §"Headless Behavior Evals (Optional)": replace Claude-only wording with provider-agnostic short blurb that links to `tests/evals/README.md` for the matrix. Keep the examples compact and include both default `--fast` and explicit Codex provider usage.
- `USAGE.md`: add `--provider` flag mention in the eval section if one exists; otherwise add a brief paragraph cross-linking to `tests/evals/README.md`. Do not duplicate the matrix.
- **NEW** `core/migrations/0.5.0/README.md` (parallel to `core/migrations/0.4.0/README.md`): documents the no-op nature of the 0.5.0 migration AND the explicit two-step upgrade requirement for 0.3.x repos (`--to 0.4.0` then `--to 0.5.0`). Keeps the upgrade-path constraint discoverable from the migration directory itself, not just the CHANGELOG.

### 6. Verification surfaces

All migration tests and provider-routing checks must pass before merge. See Verification section.

---

## Acceptance Criteria

| ID | Criterion | Verification Method |
|---|---|---|
| AC-1 | `scripts/bootstrap-request.sh` ships `template_version="0.5.0"`. | TYPECHECK (`grep -F 'template_version="0.5.0"' scripts/bootstrap-request.sh`) |
| AC-2 | `.claude-plugin/plugin.json` reports `"version": "0.5.0"`. | TYPECHECK |
| AC-3 | `.claude-plugin/marketplace.json` reports `"version": "0.5.0"` at BOTH `metadata.version` AND `plugins[0].version`. | TYPECHECK (`python3 -c 'import json; d=json.load(open(".claude-plugin/marketplace.json")); assert d["metadata"]["version"]=="0.5.0" and d["plugins"][0]["version"]=="0.5.0"'`) |
| AC-4 | `core/migrations/0.5.0/migration.json` exists, parses as JSON, has `schema_version=1`, `version=0.5.0`, `from_versions=["0.4.0"]`, `to=0.5.0`, EMPTY `safe_overwrite`, EMPTY `patches`, and `manifest_updates.replace` containing both `template_version=0.5.0` and `synced_to_template_version=0.5.0`. | AUTOMATED-INTEGRATION (small python harness) |
| AC-5 | `tests/migrations/0.5.0/run.sh` exists, is executable, and exits 0 covering `clean-from-0.4.0` + idempotency. | AUTOMATED-INTEGRATION |
| AC-6 | `tests/migrations/0.5.0/run.sh` proves the no-op contract: after `agent-sync.sh --target <fixture> --to 0.5.0 --apply`, `git status --short` in the fixture shows EXACTLY `.agent/manifest.json` and `.agent/sync-log.md` modified, and NOTHING ELSE. The sync-log entry is unconditional per `agent-sync.py:699-702`; the manifest update is the migration's only mechanical change. Any other path appearing in `git status` indicates a regression of the no-op contract. | AUTOMATED-INTEGRATION |
| AC-7 | `CHANGELOG.md` has a `## 0.5.0 - <date>` entry that references: provider abstraction, `AGENT_LLM_PROVIDER`, `CODEX_BIN`, `CODEX_EXTRA_ARGS`, `--provider` flag, no-op migration, and the required two-step upgrade for `0.3.x` repos. | TYPECHECK + MANUAL (header check via grep, content review manual) |
| AC-8 | `tests/evals/README.md` rewrite covers: provider precedence (CLI > env > default), per-provider env vars, current eval matrix (deterministic includes `codex-harness-fixture.sh`; `plugin-command-load.sh` documented as Claude-Code-specific with SKIP-on-non-claude behavior), and "Adding Evals" recipe uses `run_llm`. No remaining unconditional reference to `run_claude` in the body. | TYPECHECK (`grep -c 'run_llm\|--provider\|AGENT_LLM_PROVIDER' tests/evals/README.md` > 5) |
| AC-9 | `README.md` §"Headless Behavior Evals" no longer asserts "the Claude CLI" as the sole route; references either `--provider` or links to `tests/evals/README.md` for the matrix. | TYPECHECK |
| AC-10 | `USAGE.md` mentions `--provider` flag at least once OR cross-links to `tests/evals/README.md`. | TYPECHECK |
| AC-11 | `tests/migrations/0.3.0/run.sh` still passes (regression). | AUTOMATED-INTEGRATION |
| AC-12 | `tests/migrations/0.4.0/run.sh` still passes (regression). | AUTOMATED-INTEGRATION |
| AC-13 | `scripts/agent-validate.sh` template self-check still passes (skill count remains 7; no skill added or removed). | AUTOMATED-INTEGRATION |
| AC-14 | `python3 scripts/lib/test_validate_plan.py` still passes 27/27. | AUTOMATED-UNIT |
| AC-15 | Provider routing regressions still pass: `scripts/agent-evals.sh --fast` exits 0 (default + `AGENT_LLM_PROVIDER=codex`), `--provider unknown` exits 2, `CODEX_BIN=...mocks/codex-quota.sh --behavior --provider codex` produces 4 SKIP, `CLAUDE_BIN=...mocks/claude-quota.sh --behavior` produces 4 SKIP. | AUTOMATED-INTEGRATION |
| AC-16 | `bash -n` passes on every modified shell file: `scripts/bootstrap-request.sh`, `tests/migrations/0.5.0/run.sh`. | TYPECHECK |
| AC-17 | `scripts/agent-validate-plan.sh --strict docs/plans/llm-provider/pr-3/plan.md` exits 0 at plan creation (before code work) and produces only the expected EV-003/EV-004 drift after PR-3 lands. Same drift contract as PR-1 AC-9 / PR-2 AC-15. | AUTOMATED-UNIT |
| AC-18 | `core/migrations/0.5.0/README.md` exists, mentions the no-op nature of the migration, AND explicitly tells 0.3.x repos to run `agent-sync.sh --to 0.4.0` before `--to 0.5.0`. | TYPECHECK (`grep -E '0\.4\.0' core/migrations/0.5.0/README.md` AND `grep -F 'no-op' core/migrations/0.5.0/README.md`) |

---

## Existing Behaviors Preserved

Each entry below cites the file and line range that establishes the current behavior. No behavior in this PR is classified `INTENTIONALLY REMOVED` or `BUG FIX`. PR-3 ships zero runtime logic changes — only version metadata, docs, and the no-op migration manifest.

- **PRESERVED** — `scripts/bootstrap-request.sh` continues to bootstrap targets at the template's pinned version; only the literal version string flips. Evidence: `scripts/bootstrap-request.sh:14`.
- **PRESERVED** — `.claude-plugin/plugin.json` schema unchanged; only the version field flips. Evidence: `.claude-plugin/plugin.json:4`.
- **PRESERVED** — `.claude-plugin/marketplace.json` schema unchanged; only the two version fields flip. Evidence: `.claude-plugin/marketplace.json:8` and `.claude-plugin/marketplace.json:15`.
- **PRESERVED** — `core/migrations/<version>/migration.json` schema-1 contract unchanged. The new 0.5.0 manifest follows the existing 0.4.0 pattern. Evidence: `core/migrations/0.4.0/migration.json:1-5`.
- **PRESERVED** — `agent-sync.py` migration semantics unchanged: still single-step (no migration walker), still rejects dirty worktrees without `--allow-dirty`, still emits the sync-log audit entry on every successful apply. PR-3 only adds a new manifest under `core/migrations/0.5.0/`; no patcher logic changes. Evidence: `core/migrations/0.4.0/migration.json:1-5` (template) and `tests/migrations/0.4.0/run.sh:107-108` (production sync invocation pattern).
- **PRESERVED** — `tests/migrations/0.3.0/run.sh` and `tests/migrations/0.4.0/run.sh` continue to pass. PR-3 adds `tests/migrations/0.5.0/run.sh` without touching the older runners. Evidence: `tests/migrations/0.4.0/run.sh:1-22` (header documenting 0.3.0 → 0.4.0 scope, post-`2ee1d15`).
- **PRESERVED** — All 27 `test_validate_plan.py` cases still pass. PR-3 does not touch `scripts/lib/validate_plan.py`. Evidence: `scripts/lib/test_validate_plan.py:1-10`.
- **PRESERVED** — `scripts/agent-validate.sh` template self-check still passes. PR-3 adds no skill files. Evidence: `scripts/agent-validate.sh:227-232`.
- **PRESERVED** — All PR-1/PR-2 routing behavior continues to work: claude-default + codex routing + provider-aware SKIP wording + `--provider` CLI override + path-normalization for relative bins. PR-3 does not touch `scripts/agent-evals.sh`, `scripts/lib/llm_provider.sh`, or `tests/evals/test-helpers.sh`. Evidence: `tests/lib/test_llm_provider.sh:1-10` (49 cases continue to gate the registry contract).
- **PRESERVED** — `tests/evals/README.md` body content rewrite removes Claude-only wording but keeps the file's role as the authoritative provider matrix. Existing cross-references from `README.md` and `USAGE.md` continue to resolve. Evidence: `tests/evals/README.md:7-8` (current Claude-pinned wording) and `tests/evals/README.md:54-58` (current `run_claude` recipe).

## Verification

Pre-merge gates, in order. All must pass:

```bash
# Static checks
bash -n scripts/bootstrap-request.sh
bash -n tests/migrations/0.5.0/run.sh

# Migration manifest validity (AC-4)
python3 - <<'PY'
import json
d = json.load(open("core/migrations/0.5.0/migration.json"))
assert d["schema_version"] == 1, d
assert d["version"] == "0.5.0", d
assert d["from_versions"] == ["0.4.0"], d
assert d["to"] == "0.5.0", d
assert d.get("safe_overwrite", []) == [], d
assert d.get("patches", []) == [], d
mu = d["manifest_updates"]["replace"]
assert mu["template_version"] == "0.5.0", mu
assert mu["synced_to_template_version"] == "0.5.0", mu
print("AC-4 PASS: 0.5.0 migration manifest is well-formed no-op")
PY

# Version bumps (AC-1, AC-2, AC-3)
grep -F 'template_version="0.5.0"' scripts/bootstrap-request.sh                # AC-1
python3 -c 'import json; d=json.load(open(".claude-plugin/plugin.json")); assert d["version"]=="0.5.0"'  # AC-2
python3 -c 'import json; d=json.load(open(".claude-plugin/marketplace.json")); assert d["metadata"]["version"]=="0.5.0" and d["plugins"][0]["version"]=="0.5.0"'  # AC-3

# Migration regression (AC-5, AC-6, AC-11, AC-12)
tests/migrations/0.3.0/run.sh                                                  # AC-11
tests/migrations/0.4.0/run.sh                                                  # AC-12
tests/migrations/0.5.0/run.sh                                                  # AC-5 + AC-6

# Validators (AC-13, AC-14, AC-17)
scripts/agent-validate.sh                                                      # AC-13
python3 scripts/lib/test_validate_plan.py                                      # AC-14
scripts/agent-validate-plan.sh --strict docs/plans/llm-provider/pr-3/plan.md   # AC-17

# Provider routing regression (AC-15)
scripts/agent-evals.sh --fast                                                  # default
AGENT_LLM_PROVIDER=codex scripts/agent-evals.sh --fast                         # codex deterministic
scripts/agent-evals.sh --provider unknown 2>&1; [ "$?" = "2" ]                 # exit 2
CODEX_BIN="$(pwd)/tests/evals/mocks/codex-quota.sh" \
  scripts/agent-evals.sh --behavior --provider codex                           # 4 SKIP codex
CLAUDE_BIN="$(pwd)/tests/evals/mocks/claude-quota.sh" \
  scripts/agent-evals.sh --behavior                                            # 4 SKIP claude

# Doc surface checks (AC-7, AC-8, AC-9, AC-10, AC-18)
grep -F '## 0.5.0' CHANGELOG.md                                                # AC-7
grep -E 'AGENT_LLM_PROVIDER|--provider' CHANGELOG.md                           # AC-7
grep -F '0.4.0' CHANGELOG.md | grep -i -E 'two-step|first|before'              # AC-7 upgrade-path note present
grep -E 'AGENT_LLM_PROVIDER|--provider|run_llm' tests/evals/README.md          # AC-8
! grep -E '^[[:space:]]*-?[[:space:]]*`?run_claude`?' tests/evals/README.md    # AC-8 no run_claude in body bullets
grep -E 'tests/evals/README|--provider' README.md                              # AC-9
grep -E 'tests/evals/README|--provider' USAGE.md                               # AC-10
grep -E '0\.4\.0' core/migrations/0.5.0/README.md                              # AC-18
grep -F 'no-op' core/migrations/0.5.0/README.md                                # AC-18
```

The 0.5.0 migration test specifically asserts the no-op contract (AC-6): after sync, `git status --short` in the fixture must show EXACTLY `.agent/manifest.json` AND `.agent/sync-log.md` modified, and **nothing else**. The sync-log entry is mandatory per `agent-sync.py:699-702`; the manifest update is the migration's only mechanical change. This pair operationalizes "PR-3 does not touch any file downstream repos materialize into `.agent/`" while accounting for the unconditional audit entry.

---

## Out of Scope

- Q2 codex regex expansion: still tracked separately. Real-production sample collection is a post-0.5.0 task.
- Adding a migration walker to `agent-sync.py` (so a single `--to 0.5.0` could chain 0.3.0 → 0.4.0 → 0.5.0). Out of scope for PR-3 because PR-3 is a release-engineering wrapper with no runtime logic changes. The 0.3.x → 0.5.0 single-step path remains rejected by `agent-sync.py:155-194 load_migration`; users do the two-step `--to 0.4.0` then `--to 0.5.0` instead, documented in `core/migrations/0.5.0/README.md` and in the CHANGELOG.
- Cumulative `from_versions: ["0.3.0", "0.3.2", "0.4.0"]` for the 0.5.0 manifest. Rejected: would require duplicating every patch + safe_overwrite from `core/migrations/0.4.0/migration.json`, breaking the no-op framing and creating drift risk for future patch additions.
- New evals or new providers beyond claude + codex.
- Tagging the 0.5.0 release commit. PR-3 ships the artifact set; the maintainer creates the `v0.5.0` git tag separately after merge.

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| `tests/migrations/0.5.0/run.sh` accidentally builds a fictitious 0.4.0 fixture (the same trap the dropped `clean-from-0.3.2` fell into). | Build the 0.4.0 fixture by genuinely syncing the 0.3.0 baseline through `agent-sync.sh --to 0.4.0` first, then commit the fixture worktree (sync rejects dirty worktrees per `agent-sync.py:648-649`), then test 0.4.0 → 0.5.0. Use the production sync code as setup so the fixture state is honest by construction. |
| No-op migration silently regresses (someone adds a `safe_overwrite` entry that DOES touch downstream files in a future PR-N, breaking the 0.5.0 no-op contract). | AC-6 asserts `git status --short` shows EXACTLY `.agent/manifest.json` AND `.agent/sync-log.md` (the unconditional audit entry per `agent-sync.py:699-702`) after sync. Any third path appearing in `git status` will trip this assertion. |
| 0.3.x users get a confusing error when they try `--to 0.5.0` directly. | `core/migrations/0.5.0/README.md` (AC-18) and the CHANGELOG entry (AC-7) both document the required two-step upgrade. The error itself comes from `agent-sync.py:155-194 load_migration` and reads `migration metadata mismatch: current=0.3.0, requested=0.5.0, ...` — actionable enough to point users at the docs. A walker remains a future-PR option if pain materializes. |
| Doc rewrite drifts from runtime behavior (e.g. claims a flag that doesn't exist). | AC-8 / AC-9 / AC-10 grep against tokens that DO exist in the runtime (`--provider`, `AGENT_LLM_PROVIDER`, `run_llm`). Negative grep against `run_claude` in `tests/evals/README.md` body bullets. |
| `v0.5.0` tag does not exist at PR-3 merge time. | `tests/migrations/0.5.0/run.sh` creates an ephemeral `v0.5.0` tag at HEAD if missing (deleted on EXIT), same pattern as `tests/migrations/0.4.0/run.sh:70-72`. The maintainer creates the real tag at release time. |
| CHANGELOG entry omits a PR. | AC-7 grep checks for the headline tokens (provider abstraction, `--provider`, `AGENT_LLM_PROVIDER`, `CODEX_BIN`, `CODEX_EXTRA_ARGS`, no-op migration). Manual review covers narrative completeness. |
