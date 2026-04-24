# Release Process

This document defines release discipline for the Agent Bootstrap Template. It covers template releases, not downstream application releases.

## Version Policy

- Minor release, such as `0.2.x` to `0.3.0`: must have an annotated git tag and a `core/migrations/<version>/` directory, even when the migration is intentionally empty.
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

1. Confirm the release commit and changelog entry.
2. Add or update `core/migrations/<version>/`.
3. Add or update migration tests when the migration is non-empty.
4. Create an annotated tag at the release commit:

   ```bash
   git tag -a v<version> <commit> -m "agent-bootstrap-template <version>"
   ```

5. Record the tag-to-commit mapping in `core/release-tags.md`.
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
