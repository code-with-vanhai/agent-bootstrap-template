# Release Process

This document defines release discipline for the Agent Bootstrap Template. It covers template releases, not downstream application releases.

## Version Policy

- Minor releases must ship `core/migrations/<version>/` even when the migration is empty (`safe_overwrite` / `patches` may be `[]`). Patch releases (`0.x.(y+1)`) may omit a migration when no downstream-facing generated files changed; see the patch checklist below. Release `0.11.0` briefly shipped without a migration directory; that gap was repaired via **D-11 Option A** (`core/migrations/0.11.0/` backfill per `docs/2026-05-05-migration-ux-improvement-plan.md`).
- Patch release, such as `0.3.0` to `0.3.1`: migration is optional and is required only when downstream-facing generated files changed.
- User-facing versions use semver without a `v` prefix in manifests, migration JSON, docs, and CLI input.
- Git tags use the `v<semver>` form, for example `v0.3.0`.

## Tag Rules

- Tags are the source of truth for historical migration baselines.
- Tags must be annotated.
- Tags must point at immutable release commits recorded in `core/release-tags.md`.
- Do not retarget an existing release tag silently.
- Tag creation and `git push origin <tag>` are always human-triggered. Sync tooling must never create or push tags. The Stage 3.4 commit-message and migration-scaffold helpers (see [Conventional Commits](#conventional-commits) and [Migration Scaffold](#migration-scaffold)) are deliberately read-only and do not call `git tag` or `git push`.

## Conventional Commits

Stage 3.4 (May 2026) makes Conventional Commits a hard release gate.

- All PR commits must match `<type>(<scope>)?!?: <description>` where `<type>` is one of `feat`, `fix`, `chore`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `revert`. Subject lines are capped at 100 characters.
- Auto-generated subjects are exempt: GitHub-style `Merge pull request #...` (recognized by their `>= 2` parent commits) and `Revert "..."` (`git revert` defaults).
- The CI workflow `.github/workflows/ci.yml` job `conventional-commits` runs `python3 scripts/lib/check_conventional_commits.py --repo . --range <base>..<head>` on every pull request. Push events to `main` skip the gate so historical non-conformant subjects on `main` do not retroactively fail; the gate enforces forward discipline only.
- Run the checker locally before pushing:
  ```bash
   python3 scripts/lib/check_conventional_commits.py --range origin/main..HEAD
  ```

The helper is **Python stdlib only**: no Node toolchain, no `commitlint` install. The implementation lives in `scripts/lib/check_conventional_commits.py`; tests live in `scripts/lib/test_check_conventional_commits.py` and are wired through the existing `check_test_module_coverage.py` gate so a new test file cannot land without the matching CI invocation.

## Migration Scaffold

`scripts/scaffold-migration.sh <from> <to>` (Stage 3.4) generates a schema-v1 `migration.json` skeleton from the diff between `v<from>` and `v<to>` over **`core/`**, **`scripts/`**, and **`adapters/`** (plus an informational list of other changed paths on stderr).

- Default invocation prints the skeleton to stdout. Pass `--write` to land it at `core/migrations/<to>/migration.json`; the helper refuses to clobber an existing file unless you also pass `--force`.
- Auto-mapped target trees: `core/commands/*` → `.agent/commands/*`, `core/workflows/*` → `.agent/workflows/*`, `core/roles/**` → `.agent/roles/**`, `core/hooks/*` → `.agent/hooks/*`, and `core/<x>.template.<ext>` → `.agent/<x>.<ext>`.
- `scripts/**` entries use the canonical template layout (`source` and `target` are the same repo-relative path).
- **Test files are filtered by default.** `scripts/**/test_*.py` modules are template-only CI gates (no committed migration has ever placed one under `safe_overwrite`), so the scaffolder filters them out and surfaces the filtered paths in the stderr **Skipped** report. Pass `--include-tests` to opt back in (rare; only when you genuinely want the test module shipped downstream).
- Known `adapters/*` files map to their downstream targets exactly like `core/migrations/0.9.0/migration.json` (including `skip_if_target_missing` on optional adapters).
- Renames and deletes under `core/` emit `manifest_updates.tracked_files_remove` (Stage 3.3) for the obsolete downstream path. The directive activates on `manifest_updates.update_tracked_files: true`, which the scaffolder turns on automatically whenever it emits a removal entry.
- Anything outside those rules is emitted with `source == target` and surfaced in the stderr **Review required** report; another stderr section (**Changed outside scaffold pathspec**) lists repo-wide deltas that are outside `core/` / `scripts/` / `adapters/` (excluding a small ignore list such as `.claude-plugin/`, `tests/`, `docs/`, `.github/workflows/`) so release notes / plugin bumps cannot hide from the author entirely.
- The helper is read-only: it never tags, fetches, pushes, or rewrites refs. It calls only `git diff` and `git rev-parse --verify`. The "no silent tag push" rule above is enforced by construction, not by convention.
- Implementation: `scripts/lib/scaffold_migration.py`; tests: `scripts/lib/test_scaffold_migration.py`.

## Minor Release Checklist

1. From a clean `main`, run `scripts/bump-version.sh <version>` (Stage 2.1). This updates `scripts/bootstrap-request.sh`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` (both version slots), inserts a `## <version> - <date>` heading into `CHANGELOG.md`, and appends a semver-sorted row to `core/release-tags.md` with commit `<PENDING>`.
2. Generate the migration skeleton: `scripts/scaffold-migration.sh <prev> <version> --write`. Review the stderr "Review required" list, fill in `patches`, and replace the placeholder `notes` string with a human summary of the release.
3. Fill in `CHANGELOG.md` bullets for the release; run `scripts/agent-validate.sh` and migration fixtures.
4. Commit, create an annotated tag at the release commit:
  ```bash
   git tag -a v<version> <commit> -m "agent-bootstrap-template <version>"
  ```
5. Replace `<PENDING>` in the new `core/release-tags.md` row with the tag's commit SHA (immutable mapping per §Tag Rules).
6. Confirm `python3 scripts/lib/check_version_consistency.py --strict` passes (CI uses `--strict` so a forgotten `<PENDING>` blocks merge).
7. Push the tag manually after review:
  ```bash
   git push origin v<version>
  ```

## Patch Release Checklist

1. Confirm whether any downstream-facing generated files changed.
2. If generated files changed, add the required patch migration. `scripts/scaffold-migration.sh <prev> <version>` is the recommended starting point — it lists the diff under `core/` and emits a skeleton you can trim.
3. If only tooling/docs changed, record the patch in `CHANGELOG.md`; no migration directory is required.
4. Create and push the annotated patch tag manually when publishing the release.

## 0.3.0 Baseline Notes

The first migration-framework PR establishes these historical baselines:

- `v0.2.0` at `2db730164d2d44cc343c1556c975c27d8a5efa32`.
- `v0.3.0` at `fd30e86d68a91786b39af85dcf3bfce8a3000c1e`.

The tags must exist before PR 2 migration preflight can pass.