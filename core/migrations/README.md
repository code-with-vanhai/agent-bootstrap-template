# Migration Framework — Design Plan

Status: **implemented for schema v1 and 0.2.0 -> 0.3.0**. Review locked on 2026-04-24; implementation added in 0.3.1.

This document captures the locked design for versioned migration of downstream repositories that consume the Agent Bootstrap Template. It is the source of truth for the upcoming implementation; every open question has either been answered or explicitly deferred to schema v2.

---

## 1. Motivation

Downstream repos (e.g. `brainmap-extension`) consume the template once via `bootstrap-request.sh`, then diverge as the template evolves. Manual per-file sync does not scale:

- Commands get overwritten without customization detection.
- Surgical patches to files like `scripts/agent-eval.sh` are easy to corrupt.
- Version tracking drifts silently.
- No test coverage for the migration itself.

The goal is a deterministic, reviewable, safe upgrade path from template version N to version M.

**Hard bar:** the sync tool must refuse conflicts by default. Silent overwrite of customized downstream files is not acceptable at any point.

---

## 2. Scope (MVP)

**In:**

1. Git tags as baseline storage (`v0.2.0`, `v0.3.0`).
2. Declarative migration manifest (`core/migrations/<version>/migration.json`).
3. Generic runner: `scripts/agent-sync.sh` (bash wrapper) + `scripts/agent-sync.py` (Python helper).
4. 3-way merge logic for `safe_overwrite`.
5. Anchored, idempotent patches.
6. Codex command-wrapper skill generation derived from `core/commands/*.md`.
7. Declarative manifest updates with `append_to_array_unique` idempotency.
8. Append-only `.agent/sync-log.md` in target.
9. Mechanical migration test under `tests/migrations/<version>/`.
10. Fixture regeneration procedure documented (not auto-regenerated).
11. Explicit per-file `--accept-theirs <path>` conflict escape hatch, logged on apply.

**Deferred to schema v2:**

- File delete / rename operations.
- `/agent-bootstrap:sync` slash command.
- Default auto-running of real gates post-migration. MVP only supports explicit `--verify-fast`.
- Cross-minor chain migration beyond one hop.

---

## 3. Locked Decisions

### 3.1 Baseline storage — git tags

Tags are the single source of historical truth. The template must tag every minor release.

```bash
git tag -a v0.2.0 2db7301 -m "agent-bootstrap-template 0.2.0"
git tag -a v0.3.0 fd30e86 -m "agent-bootstrap-template 0.3.0"
git push origin v0.2.0 v0.3.0
```

Verified commits: `.claude-plugin/plugin.json` at 2db7301 is `"version": "0.2.0"` and `CHANGELOG.md` at 2db7301 already contains the 0.2.0 entry. 2db7301 is the last commit on the 0.2.0 line before b58ba02 started 0.3.0 feature work. fd30e86 is the 0.3.0 release commit.

Runner requires both tags to exist before apply. Fails early if either is missing.

### 3.2 Migration format — declarative JSON

No per-migration `migration.sh` in schema v1. A generic runner parses `migration.json`. Escape hatch for custom logic is deferred.

### 3.3 Conflict policy — stop-and-report

No `.conflict` files. No auto-merge. No `.bak`. On conflict, the runner prints per-file base/theirs/ours hashes and the exact `diff` commands to inspect divergence, then aborts with zero writes.

### 3.4 Test strategy — `tests/migrations/<version>/`

Fully mechanical; separated from `scripts/agent-evals.sh` (which is behavior/model eval). No model tokens consumed.

### 3.5 Release process — tag-for-minor

- Minor bump (`0.2.x` → `0.3.0`): **mandatory** tag and `core/migrations/<version>/` directory, even if migration is empty.
- Patch bump (`0.3.0` → `0.3.1`): migration optional; skipped if no downstream-facing files changed.

### 3.6 Version string normalization

User-facing version strings are semver without a `v` prefix. This applies to CLI input, `migration.json` `from`/`to`/`version`, `.agent/manifest.json`, and `.agent/sync-log.md`.

- Valid version regex: `^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$`.
- Invalid: `v0.3.0`, `0.3`, `0.3.0+build.1`.
- Git tag resolution is the only place where the runner adds the prefix: `0.3.0` resolves to tag `v0.3.0`.
- Error messages should print both forms when useful, e.g. `version 0.3.0 requires tag v0.3.0`.

### 3.7 Adapter file policy

Adapter entrypoints are intentionally high-customization files: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.cursor/rules/agent-system.mdc`, and `.github/copilot-instructions.md`.

Schema v1 does **not** include adapters in default `safe_overwrite`. A migration may define an `adapter_files` block for reporting, but the runner only applies adapter overwrites when the user passes `--with-adapters`. The 0.2.0 -> 0.3.0 migration does not need adapter overwrites because adapter sources did not change between 2db7301 and fd30e86.

---

## 4. Runner behavior

### 4.1 CLI

```bash
scripts/agent-sync.sh --target <path> --to <version>        # dry-run (default)
scripts/agent-sync.sh --target <path> --to <version> --apply # write
scripts/agent-sync.sh --target <path> --to <version> --apply --accept-theirs .agent/commands/verify.md
```

Flags:

| Flag | Meaning |
|------|---------|
| `--target <path>` | Required. Target repository root. |
| `--to <version>` | Optional. Default: latest available migration. |
| `--apply` | Required to write. Absence means dry-run. |
| `--allow-dirty` | Permit dirty target worktree. Default: reject. |
| `--template-root <path>` | Override template repo path. Default: script parent. |
| `--verify-fast` | Run `scripts/agent-eval.sh fast` after apply. Opt-in. |
| `--with-adapters` | Allow adapter files to be included if a migration declares `adapter_files`. Default: report only. |
| `--accept-theirs <path>` | Explicitly overwrite one conflicted target path with the template `to` version. May be repeated. Each accepted path is logged. |

### 4.2 Pre-flight checks

In order, fail-fast:

1. Template root resolves and is a git repo.
2. Python dependency is present: `python3 --version` must be 3.8 or newer.
3. `--to`, migration `from`, migration `to`, and detected current version validate as semver without `v` prefix.
4. `v<from>` and `v<to>` tags exist in the template repo (suggest `git fetch --tags` on failure).
5. Target exists and is a git repo.
6. Target worktree is clean, unless `--allow-dirty`.
7. `.agent/manifest.json` exists in target.
8. Current version resolvable via fallback chain:
   ```
   synced_to_template_version
     → instantiated_from_template_version
     → fail "cannot detect current template version"
   ```
9. If `current == to`: no-op, exit 0.
10. Migration path `current → to` exists in `core/migrations/`.
11. If `--apply`, acquire `.agent/.sync.lock` with exclusive create before computing writes. The lock file contains PID, timestamp, `from`, and `to`. If the lock already exists, fail and tell the user to inspect/remove it only after confirming no sync process is running.

### 4.3 Apply order (fixed)

Per migration, in order:

1. `safe_overwrite` — 3-way merge on listed files.
2. `patches` — anchored insert with idempotency.
3. `generate_codex_command_wrappers` — derived from `core/commands/*.md`.
4. `manifest_updates` — replace, append_unique, merge_unique.
5. Runner implicit: set `synced_at` to `AGENT_SYNC_NOW` env var or current UTC ISO8601.
6. Read-only orphan report for files present in managed target directories but absent from the `to` template file set.
7. Append entry to `.agent/sync-log.md`.

Order is fixed because patches may depend on a file just overwritten (e.g. patch target is in `safe_overwrite`).

### 4.4 Transactional write

Runner computes the full change set in memory and performs all conflict checks before the first target-content write. The only earlier write allowed is the advisory `.agent/.sync.lock` for `--apply`. If any conflict, no content writes happen. If post-apply validation fails, runner prints:

```
Migration applied but validation failed. To revert:
  git -C <target> restore .
  git -C <target> clean -fd
```

No `.bak`. No auto-revert. Target's clean-worktree guard ensures this is always a valid recovery path.

The advisory lock is removed on successful apply, failed apply, dry-run bypass, or handled error. If the process is killed and leaves a stale lock, the next run must stop and print the lock contents.

Post-apply validation must run against the target repo, never accidentally against the template source repo. The runner must either set `AGENT_ROOT=<target>` when invoking `<target>/scripts/agent-validate.sh` or run the validator with current directory set to `<target>`. This prevents nested migration fixtures under `tests/migrations/.../before/` from affecting template-source validation.

### 4.5 Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success (or no-op) |
| 1 | Unknown/internal error |
| 2 | Usage error (missing flag, invalid version string) |
| 10 | Target worktree dirty; needs `--allow-dirty` |
| 20 | Conflict detected; aborted before writes |
| 30 | Post-apply validation failed |
| 40 | No migration path found |
| 50 | Sync lock already exists |

---

## 5. 3-way merge logic

For every file in `safe_overwrite`:

```
base   = git -C <template> show v<from>:<source_path>   (or missing)
ours   = <target>/<target_path>           (or missing)
theirs = git -C <template> show v<to>:<source_path>

if ours == theirs:
    no-op
elif base exists and ours == base:
    write theirs
elif base missing and ours missing:
    create theirs               # new file in this version
elif target_path is listed in --accept-theirs:
    write theirs and log explicit override
else:
    conflict                     # stop migration
```

Comparison is **byte-exact**. No whitespace or line-ending normalization. False-positive conflicts are acceptable; silent merges are not.

Schema v1 does not support `theirs missing`. If a migration manifest references a source that does not exist at `target_ref`, the runner fails with a config error.

### `source_glob` expansion

`source_glob` is deterministic and tag-based:

- Pattern syntax is non-recursive shell-style glob within a single directory, e.g. `core/commands/*.md`. `**` is invalid in schema v1.
- The runner enumerates matches from the `to` tag, not the template working tree. Use `git -C <template> ls-tree` / `git show` against `v<to>` so uncommitted template files cannot affect migration output.
- For each `to` match, the runner checks the same `source_path` at `v<from>` to determine whether `base` exists.
- If a file matches at `v<to>` but not at `v<from>`, it follows the normal `base missing` branch: create when `ours` is missing; no-op when `ours == theirs`; conflict otherwise.
- Target paths use `target_dir` plus the source basename. Example: `core/commands/verify.md` maps to `.agent/commands/verify.md`.
- If two manifest entries map to the same target path, fail with a config error before conflict checks.
- Managed target directories for orphan reporting are exactly the `target_dir` values declared by active `safe_overwrite` `source_glob` entries, plus active generated-output namespaces. Single-file `source`/`target` entries do not create a managed directory. For Codex command wrappers, the managed namespace is `generate_codex_command_wrappers.target_dir` filtered to direct child directories whose names start with `agent-`, so existing base skills in the same skill package are not reported as orphans.
- Files that existed in a managed target directory but are absent from the `to` source set are **not deleted** in schema v1. The runner reports them as "review manually" orphans.

### Edge cases (schema v1 policy)

| Case | Policy |
|------|--------|
| `ours` missing, `base` present, `theirs` present | Conflict — downstream deliberately removed the file |
| `ours` present, `base` missing, `theirs` present, `ours != theirs` | Conflict — target pre-created the file with different content |
| `ours` present, `base` missing, `theirs` present, `ours == theirs` | No-op |
| `theirs` missing (template deleted) | Config error (deferred to v2) |

---

## 6. Patch logic

Declarative, anchored, idempotent:

```json
{
  "file": "scripts/agent-eval.sh",
  "anchor": "gate=\"${1:-fast}\"",
  "insert_after_first_match": "if [ \"$#\" -gt 1 ]; then\n  printf 'Usage: %s [changed|fast|frontend|backend|shared|e2e|full|security|release]\\n' \"$0\" >&2\n  printf 'Received unsupported extra arguments: %s\\n' \"$*\" >&2\n  exit 1\nfi\n",
  "skip_if_contains": "Received unsupported extra arguments",
  "require_bash_syntax_ok_after": true
}
```

Runner logic:

1. If `skip_if_contains` already present in file → no-op, log skip.
2. Search for literal matches of `anchor`. If zero matches → conflict. If more than one match → conflict because the patch anchor is ambiguous.
3. Insert `insert_after_first_match` immediately after the unique matched line.
4. If `require_bash_syntax_ok_after` is true, run `bash -n` on the patched file in a tempfile before committing the write. Fail → conflict.

Migration authors should use anchors with enough context to be unique in realistic downstream files. One fragile line is acceptable only when the runner proves it appears exactly once.

---

## 7. `migration.json` schema v1

```json
{
  "schema_version": 1,
  "version": "0.3.0",
  "from": "0.2.0",
  "to": "0.3.0",

  "safe_overwrite": [
    {
      "source_glob": "core/commands/*.md",
      "target_dir": ".agent/commands"
    },
    {
      "source": "scripts/agent-validate.sh",
      "target": "scripts/agent-validate.sh"
    }
  ],

  "adapter_files": [],

  "patches": [
    {
      "file": "scripts/agent-eval.sh",
      "anchor": "gate=\"${1:-fast}\"",
      "insert_after_first_match": "...",
      "skip_if_contains": "Received unsupported extra arguments",
      "require_bash_syntax_ok_after": true
    }
  ],

  "generate_codex_command_wrappers": {
    "enabled_when_feature_present": "native-skills",
    "commands_source_glob": "core/commands/*.md",
    "target_dir": ".agents/skills/agent-bootstrap"
  },

  "manifest_updates": {
    "replace": {
      "template_version": "0.3.0",
      "synced_to_template_version": "0.3.0"
    },
    "replace_from_git_tag": {
      "synced_to_template_commit": "0.3.0"
    },
    "append_to_array_unique": {
      "notes": "Synced to agent-bootstrap-template v0.3.0: added refactor/security-review commands, Codex command-wrapper skills, verify extra-argument rejection, and command permission hardening notes."
    },
    "merge_array_unique": {}
  }
}
```

### Notes on manifest_updates

- `replace`: create-or-overwrite scalar field (upsert). Existing keys keep their current object position. New sync metadata keys are inserted immediately after `instantiated_from_template_version`, in this order: `synced_to_template_version`, `synced_to_template_commit`, `synced_at`.
- `replace_from_git_tag`: value is a normalized semver without `v`; the runner resolves it to tag `v<version>`, then writes the full commit SHA from `git rev-parse v<version>^{commit}`. This resolver shares the pre-flight tag existence check in section 4.2; missing tags must fail before manifest writes are computed.
- `append_to_array_unique`: append string iff no existing array entry contains the exact string (substring check; prevents duplicate notes on re-apply).
- `merge_array_unique`: add list items not already present.
- `synced_at` is always set by the runner, never listed in `migration.json`. Value comes from `AGENT_SYNC_NOW` env var (if set) else current UTC ISO8601.
- `template_version` is updated to the current installed template version. `instantiated_from_template_version` remains the original bootstrap version and is never overwritten by sync.

### Notes on adapter_files

- `adapter_files` is optional. It uses the same `source`/`target` object shape as `safe_overwrite`.
- Adapter files are report-only unless the CLI includes `--with-adapters`.
- When `--with-adapters` is present, adapter files use the same byte-exact 3-way merge and `--accept-theirs` rules as `safe_overwrite`.
- The 0.2.0 -> 0.3.0 migration keeps this empty.

---

## 8. `.agent/sync-log.md` format

Append-only, created on first successful apply. Not written on dry-run or failed apply.

```markdown
# Sync Log

## 2026-04-23T11:07:03Z — Sync to 0.3.0

- From: 0.2.0
- To: 0.3.0
- Template commit: fd30e86
- Updated:
  - .agent/commands/*.md (9 files)
  - scripts/agent-validate.sh
  - scripts/agent-eval.sh patched extra-arg guard
  - .agents/skills/agent-bootstrap/agent-*/SKILL.md generated (9 files)
  - .agent/manifest.json synced metadata
- Accepted theirs:
  - none
- Preserved:
  - .agent/project-profile.md
  - .agent/gates.md
  - .agent/ownership.md
  - scripts/agent-eval.sh npm gates
- Warnings:
  - no managed-directory orphan files
- Validation:
  - agent-validate: passed
  - bash -n agent-eval.sh: passed
```

---

## 9. Testing

### 9.1 Directory layout

```
tests/migrations/0.3.0/
├── before/          # fixture repo at v0.2.0 state
├── after/           # expected state after migration
└── run.sh           # mechanical regression test
```

### 9.2 Fixture generation (manual, one-time)

Hand-crafted minimal fixtures drift. Generate deterministically from the v0.2.0 tag:

```bash
template_repo=/home/wsladmin/agent-bootstrap-template
worktree=/tmp/template-v0.2.0
target=/tmp/fixture-before
dest="$template_repo/tests/migrations/0.3.0/before"

git -C "$template_repo" worktree add -q "$worktree" v0.2.0

rm -rf "$target" && mkdir -p "$target" && cd "$target"
git init -q

"$worktree/scripts/bootstrap-request.sh" \
  --template "$worktree" \
  --target . \
  --features full \
  --harness codex

rm .agent/bootstrap-pending.md   # fixture assumes agent completed bootstrap
rm -rf "$target/.git"

rm -rf "$dest" && mkdir -p "$dest"
cp -r "$target"/. "$dest"/

git -C "$template_repo" worktree remove "$worktree"
rm -rf "$target"
```

The `after/` fixture is generated the same way but against `v0.3.0`. Both get committed to the template repo. Regenerate only when the tag they pin changes (should never happen for a released tag).

### 9.3 `run.sh` behavior

```bash
#!/usr/bin/env bash
set -euo pipefail

root="$(git rev-parse --show-toplevel)"
work="$(mktemp -d)"
cp -r "$root/tests/migrations/0.3.0/before/." "$work/"
( cd "$work" && git init -q && git add . && git commit -q -m "fixture" )

AGENT_SYNC_NOW=2026-04-23T00:00:00Z \
  "$root/scripts/agent-sync.sh" \
  --target "$work" \
  --to 0.3.0 \
  --apply

# Commit the first apply so the second run exercises idempotency under the
# normal clean-worktree pre-flight guard.
( cd "$work" && git add . && git commit -q -m "first apply" )

# Idempotency check — second run must be a no-op
AGENT_SYNC_NOW=2026-04-23T00:00:00Z \
  "$root/scripts/agent-sync.sh" \
  --target "$work" \
  --to 0.3.0 \
  --apply

diff -r "$root/tests/migrations/0.3.0/after/" "$work/" \
  --exclude=.git
```

Idempotency is mandatory: second apply must run against a clean worktree and produce no changes (skip_if_contains for patch, no-op for 3-way where ours==theirs, append_unique for notes).

When testing from the template repo root, validator calls for fixture repos must use `AGENT_ROOT="$work"` or run from inside `$work`. The existing validator honors `AGENT_ROOT`; otherwise it chooses template-source mode from the current root and does not recursively scan nested `tests/migrations/**/.agent` directories.

---

## 10. Implementation plan

### PR 1 — Release discipline (small, mergeable immediately)

- Create `v0.2.0` tag at 2db7301 (annotated).
- Create `v0.3.0` tag at fd30e86 (annotated).
- Push tags to origin (user-triggered, not automated).
- Add `core/release-process.md` documenting tag-for-minor policy.
- Add or update `core/release-tags.md` with fixed release commit mapping (`v0.2.0=2db7301`, `v0.3.0=fd30e86`) and tag recovery commands.
- No code changes.

### PR 2 — Migration framework

- `scripts/agent-sync.sh` — bash wrapper (~30 LOC): flag parsing, pre-flight, delegate to Python.
- `scripts/agent-sync.py` — runner (~300 LOC, Python 3.8+ stdlib only): JSON parse, 3-way merge, patch, generate, manifest ops, log append.
- `core/migrations/0.3.0/migration.json` — matches section 7 schema.
- `tests/migrations/0.3.0/{before,after,run.sh}` — fixtures generated per section 9.2.
- Update `USAGE.md` with a "Syncing existing repos" section.
- Update `CHANGELOG.md` with `0.3.1` (framework only, no downstream behavior change).

---

## 11. Resolved final-review decisions

1. **Push tags to origin:** user-triggered, never automated by the sync runner.
2. **PR split:** two PRs. PR 1 is release discipline and tags; PR 2 is the migration framework and tests.
3. **Version bump for framework:** `0.3.1` patch, because the framework adds sync tooling without changing newly generated repo behavior.

---

## 12. Out-of-scope (explicitly)

To keep MVP focused, these are intentionally not covered:

- Parallel migration orchestration across multiple target repos. Same-target concurrent apply is blocked by `.agent/.sync.lock`.
- Rollback to an earlier version (`--to 0.2.0` when current is 0.3.0).
- Migration dry-run that simulates validator output.
- Interactive conflict resolution UI.
- Cross-platform Python packaging (script is bash+python, runs on Linux/macOS).
- Automated fixture regeneration on every template commit.

Each is a reasonable v2+ feature; none is required to retire the manual-sync pattern.
