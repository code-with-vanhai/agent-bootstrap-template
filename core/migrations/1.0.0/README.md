# Migration: 0.11.0 → 1.0.0

## Source acceptance

This migration accepts only `0.11.0` as a source version
(`from_versions: ["0.11.0"]`).

Repos still on earlier versions must apply each intermediate migration
first. The auto multi-hop walker (Stage 1.1) will compose the chain
automatically when only `--to 1.0.0` is given, provided every hop's
`v<from>` and `v<to>` tags are reachable in the template repo.

## What this migration ships

**No downstream content patches.** `safe_overwrite` and `patches` are
both empty, mirroring the no-op shape of `core/migrations/0.5.0` and
`core/migrations/0.11.0`.

The substantive change is opt-in to the
[`tracked_files` writer (Stage 3.1)](../README.md#notes-on-tracked_files)
via the new `manifest_updates.update_tracked_files: true` flag, plus the
**one-shot backfill** introduced in Stage 3.3 of
`docs/2026-05-05-migration-ux-improvement-plan.md`. Concretely, on the
first `0.11.0 → 1.0.0` apply the runner will:

1. Enumerate the union of every `expand_file_entries` row for this
   migration plus every path under `manifest.canonical_files`.
2. For each existing managed file on disk, compute `sha256(disk)` and
   record `manifest.tracked_files[<path>] = {synced_at_version:
   "0.11.0", synced_checksum_sha256: <sha>}`.
3. Pre-existing `tracked_files` entries that are not part of the
   backfill scope are preserved verbatim.

The recorded version is intentionally `0.11.0` (the user's current
sync version at backfill time), not blindly `1.0.0`. The bytes hashed
are what the user has on disk right now; that is the baseline that
should drive the Stage 3.2 checksum fast-path going forward.

After the backfill, the Stage 3.1 writer refreshes any path that the
hop actually rewrites (none in this version, since `safe_overwrite` is
empty) so future migrations can layer further refreshes cumulatively.

## What this migration does NOT do

- It does not modify any downstream file outside `.agent/manifest.json`
  and `.agent/sync-log.md`. Re-applying after a successful sync is a
  clean no-op (current-version shortcut), exactly like 0.11.0.
- It does not author a `manifest_updates.tracked_files_remove`
  directive — no managed file has been relocated or deleted between
  0.11.0 and 1.0.0. The directive is documented in
  `core/migrations/README.md` (Notes on `tracked_files`) so future
  migrations that DO relocate a tracked file can use it instead of
  abusing `replace: null`.

## Verification

`tests/migrations/checksum-backfill/run.sh` covers the backfill
post-condition, and `tests/migrations/checksum-refresh/run.sh` covers
the cumulative refresh contract using a synthetic post-1.0.0 hop.

The manifest-only no-op contract (`git status --short` reports exactly
`.agent/manifest.json` and `.agent/sync-log.md` after apply) is the
same one `tests/migrations/0.11.0/run.sh` and
`tests/migrations/0.5.0/run.sh:119` lock for their respective hops.
