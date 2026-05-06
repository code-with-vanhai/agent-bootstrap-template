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
- Tag creation and `git push origin <tag>` are always human-triggered. Sync tooling must never create or push tags. The Stage 3.4 commit-message, migration-scaffold, and release-prep helpers (see [Conventional Commits](#conventional-commits), [Migration Scaffold](#migration-scaffold), and [Release Prep Scaffold](#release-prep-scaffold)) are deliberately read-only with respect to refs and do not call `git tag` or `git push`.

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
- `scripts/**` entries use the canonical template layout (`source` and `target` are the same repo-relative path), except that `scripts/<...>/<name>.template.<ext>` is target-stripped to `scripts/<...>/<name>.<ext>` (matching the `core/<x>.template.<ext>` rule and `core/migrations/0.9.0/migration.json`).
- **Test files are filtered by default.** `scripts/**/test_*.py` modules are template-only CI gates (no committed migration has ever placed one under `safe_overwrite`), so the scaffolder filters them out and surfaces the filtered paths in the stderr **Skipped** report. Pass `--include-tests` to opt back in (rare; only when you genuinely want the test module shipped downstream).
- Known `adapters/*` files map to their downstream targets exactly like `core/migrations/0.9.0/migration.json` (including `skip_if_target_missing` on optional adapters).
- `core/skills/<skill>/<...>` source files emit **two** `safe_overwrite` rows — one under `.agents/skills/agent-bootstrap/` and one under `.claude/skills/agent-bootstrap/` — each guarded by `enabled_when_path_exists` matching its downstream root. Top-level files under `core/skills/` (`README.md`, `manifest.json`) are template-internal and stay skipped.
- Renames and deletes under `core/` emit `manifest_updates.tracked_files_remove` (Stage 3.3) for the obsolete downstream path. The directive activates on `manifest_updates.update_tracked_files: true`, which the scaffolder turns on automatically whenever it emits a removal entry.
- Anything outside those rules is emitted with `source == target` and surfaced in the stderr **Review required** report; another stderr section (**Changed outside scaffold pathspec**) lists repo-wide deltas that are outside `core/` / `scripts/` / `adapters/` (excluding a small ignore list such as `.claude-plugin/`, `tests/`, `docs/`, `.github/workflows/`) so release notes / plugin bumps cannot hide from the author entirely.
- The helper is read-only: it never tags, fetches, pushes, or rewrites refs. It calls only `git diff` and `git rev-parse --verify`. The "no silent tag push" rule above is enforced by construction, not by convention.
- Implementation: `scripts/lib/scaffold_migration.py`; tests: `scripts/lib/test_scaffold_migration.py`.

## Release Prep Scaffold

`scripts/release-prepare.sh` (Stage 3.4) is the mechanical-release helper that replaces the npm `semantic-release` toolchain in our Python-stdlib-only world. It reads commits in `<latest-tag>..HEAD`, derives the next semver bump from Conventional Commits markers (`feat!`, `fix!`, or a `BREAKING CHANGE:` trailer → major; any `feat:` → minor; otherwise patch), and produces a draft `CHANGELOG.md` body grouped by commit type.

- Default invocation is **dry-run**: prints the plan to stdout and writes nothing. Pass `--apply` to run `scripts/bump-version.sh <next>` and patch the new CHANGELOG entry's empty `- ` placeholder with the generated draft. The next steps after `--apply` (commit, annotated tag, `<PENDING>` backfill, `git push origin v<next>`) remain human-triggered per §Tag Rules.
- Pass `--bump major|minor|patch` to override the auto-derivation; the plan output records this as `bump_source: override`. `--json` emits the same plan as a machine-readable document for CI introspection.
- The helper refuses `--apply` when the commit range contains Conventional Commits violations (the same gate the `conventional-commits` CI job enforces). Pass `--allow-violations` to override, but prefer rebasing the offending subjects.
- **Read-only with respect to git**: never calls `git tag`, `git push`, `git commit`, or `git fetch`. File mutations are bounded to `bump_version.bump` (the five canonical version sources + `core/release-tags.md`) and one CHANGELOG patch. Tests assert HEAD and tag list are byte-identical before/after `--apply`.
- Implementation: `scripts/lib/release_prepare.py`; tests: `scripts/lib/test_release_prepare.py`.

## Minor Release Checklist

1. From a clean `main`, preview the next version: `scripts/release-prepare.sh` (dry-run). The plan reports the current version, the auto-derived bump, the next semver, the CHANGELOG draft, and any Conventional Commits violations.
2. Apply the mechanical bump: `scripts/release-prepare.sh --apply` (or run `scripts/bump-version.sh <version>` directly if you prefer a manual semver pick). Both routes call the same `scripts/lib/bump_version.py` helper to update `scripts/bootstrap-request.sh`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` (both version slots), insert a `## <version> - <date>` heading into `CHANGELOG.md`, and append a semver-sorted row to `core/release-tags.md` with commit `<PENDING>`. The release-prep route additionally replaces the empty `- ` placeholder with a draft body grouped by commit type so the author starts from real commit data.
3. Generate the migration skeleton: `scripts/scaffold-migration.sh <prev> <version> --write`. Review the stderr "Review required" list, fill in `patches`, and replace the placeholder `notes` string with a human summary of the release.
4. Edit the CHANGELOG draft into the project's prose style (re-organize bullets, add context, drop noise); run `scripts/agent-validate.sh` and migration fixtures.
5. Commit, create an annotated tag at the release commit:
  ```bash
   git tag -a v<version> <commit> -m "agent-bootstrap-template <version>"
  ```
6. Replace `<PENDING>` in the new `core/release-tags.md` row with the tag's commit SHA (immutable mapping per §Tag Rules).
7. Confirm `python3 scripts/lib/check_version_consistency.py --strict` passes (CI uses `--strict` so a forgotten `<PENDING>` blocks merge).
8. Push the tag manually after review:
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