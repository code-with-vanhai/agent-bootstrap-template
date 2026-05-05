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
- Tag creation and `git push origin <tag>` are always human-triggered. Sync tooling must never create or push tags.

## Minor Release Checklist

1. From a clean `main`, run `scripts/bump-version.sh <version>` (Stage 2.1). This updates `scripts/bootstrap-request.sh`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` (both version slots), inserts a `## <version> - <date>` heading into `CHANGELOG.md`, and appends a semver-sorted row to `core/release-tags.md` with commit `<PENDING>`.
2. Fill in `CHANGELOG.md` bullets for the release; run `scripts/agent-validate.sh` and migration fixtures.
3. Commit, create an annotated tag at the release commit:

   ```bash
   git tag -a v<version> <commit> -m "agent-bootstrap-template <version>"
   ```

4. Replace `<PENDING>` in the new `core/release-tags.md` row with the tag's commit SHA (immutable mapping per §Tag Rules).
5. Confirm `python3 scripts/lib/check_version_consistency.py --strict` passes (CI uses `--strict` so a forgotten `<PENDING>` blocks merge).
6. Push the tag manually after review:

   ```bash
   git push origin v<version>
   ```

## Patch Release Checklist

1. Confirm whether any downstream-facing generated files changed.
2. If generated files changed, add the required patch migration.
3. If only tooling/docs changed, record the patch in `CHANGELOG.md`; no migration directory is required.
4. Create and push the annotated patch tag manually when publishing the release.

## 0.3.0 Baseline Notes

The first migration-framework PR establishes these historical baselines:

- `v0.2.0` at `2db730164d2d44cc343c1556c975c27d8a5efa32`.
- `v0.3.0` at `fd30e86d68a91786b39af85dcf3bfce8a3000c1e`.

The tags must exist before PR 2 migration preflight can pass.
