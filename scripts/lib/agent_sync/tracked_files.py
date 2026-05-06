"""``manifest.tracked_files`` schema helpers (Stage 3.1 / 3.3).

This module owns the schema, the post-plan writer (Stage 3.1), the
one-shot disk backfill (Stage 3.3), and the explicit removal directive
(``manifest_updates.tracked_files_remove``) introduced alongside the
1.0.0 backfill. It intentionally lives in its own file rather than
inside :mod:`manifest_ops` so the fast-path / backfill follow-ups can
extend the schema without bloating manifest write planning.

Schema (additive; absence ⇒ no change):

    {
      "tracked_files": {
        ".agent/rulebase.md": {
          "synced_at_version": "0.10.0",
          "synced_checksum_sha256": "abc123..."
        }
      }
    }

Activation contract:

The runner only populates / removes ``tracked_files`` when the active
migration's ``manifest_updates`` block sets
``update_tracked_files: true``. Migrations strictly before 1.0.0 do
NOT set the flag, so legacy fixtures (e.g. ``tests/migrations/0.3.0/
after/.agent/manifest.json``) keep their byte-exact post-apply state
because nothing ever adds the ``tracked_files`` key.

Stage 3.3 layers two additional behaviors on top of the Stage 3.1
writer:

  - **One-shot backfill (:func:`backfill_tracked_files`).** Enumerates
    ``expand_file_entries`` for the active migration *plus* every path
    in ``manifest.canonical_files`` and, for each existing managed
    file on disk, records ``{synced_at_version: <current>,
    synced_checksum_sha256: sha256(disk)}`` BEFORE the write planner
    runs. The Stage 3.1 writer then refreshes touched-file entries to
    ``synced_at_version: <to>``. Pre-existing entries for paths the
    backfill does not touch are preserved verbatim so the map stays
    cumulative across hops.

  - **Explicit removal (:func:`apply_tracked_files_remove`).** Honors
    ``manifest_updates.tracked_files_remove: ["<old/path>", ...]``. The
    rationale is documented in ``core/migrations/README.md``: schema
    v1's ``replace`` directive only does top-level scalar upsert and
    cannot delete a nested key, so a future migration that relocates a
    managed file MUST author this directive instead of leaning on
    ``replace: null`` (which silently no-ops at the writer layer).
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict


TRACKED_FILES_KEY = "tracked_files"
UPDATE_TRACKED_FILES_FLAG = "update_tracked_files"
TRACKED_FILES_REMOVE_KEY = "tracked_files_remove"

# Skipped because ``.agent/manifest.json`` is the manifest itself; tracking
# its own checksum here would require a fixed-point computation. ``sync-log``
# is not a managed-file write target either.
_TRACKED_FILES_SKIP_PATHS = frozenset(
    {".agent/manifest.json", ".agent/sync-log.md"}
)


def _sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def should_update_tracked_files(migration):
    """Return True iff this migration opts into ``tracked_files`` writes.

    The flag lives under ``manifest_updates.update_tracked_files`` so it
    is colocated with the other manifest-mutation directives. Anything
    other than literal ``True`` (e.g. omitted, ``False``, ``"yes"``) is
    treated as "do not touch ``tracked_files``" — defensive against
    accidental string values from hand-edited migration JSON.
    """

    updates = migration.get("manifest_updates") or {}
    return updates.get(UPDATE_TRACKED_FILES_FLAG) is True


def compute_tracked_record(content_bytes, version):
    """Return the ``tracked_files`` value for one path.

    Public so Stage 3.3's eventual one-shot backfill can reuse the same
    record shape from a different call site without re-implementing the
    sha256 / version pairing.
    """

    return OrderedDict(
        synced_at_version=version,
        synced_checksum_sha256=_sha256_hex(content_bytes),
    )


def populate_tracked_files(manifest, migration, writes):
    """Return ``manifest`` with ``tracked_files`` updated for this hop.

    No-op when the migration has not opted in or the writes dict is
    empty. Always returns the (possibly mutated) ``manifest`` so the
    caller can chain it through :func:`ordered_manifest_with_sync`
    without a conditional.

    The function preserves any pre-existing ``tracked_files`` entries
    untouched when their path is not part of this hop's writes (e.g. a
    later migration only touches one file but the manifest already
    tracked others). This keeps the map cumulative across hops.
    """

    if not should_update_tracked_files(migration):
        return manifest
    if not writes:
        return manifest

    to_version = migration.get("to")
    if not isinstance(to_version, str) or not to_version:
        return manifest

    existing = manifest.get(TRACKED_FILES_KEY)
    if isinstance(existing, dict):
        tracked = OrderedDict(existing)
    else:
        tracked = OrderedDict()

    for rel in sorted(writes):
        if rel in _TRACKED_FILES_SKIP_PATHS:
            continue
        new_bytes = writes[rel]
        if not isinstance(new_bytes, (bytes, bytearray)):
            continue
        tracked[rel] = compute_tracked_record(bytes(new_bytes), to_version)

    manifest[TRACKED_FILES_KEY] = tracked
    return manifest


def collect_backfill_paths(entries, manifest):
    """Return the de-duplicated set of paths the backfill should consider.

    Sources, in this order so callers can reason about precedence in
    ``populate_tracked_files``:

    1. ``entries`` — every ``expand_file_entries`` row's downstream
       ``target`` path. This catches anything the active migration
       declares (``safe_overwrite``, ``adapter_files``, etc.) regardless
       of whether it ends up in the hop's ``writes``.
    2. ``manifest.canonical_files`` — the pre-1.0.0 source of truth for
       the managed scope. Including it guarantees that even repos
       whose Stage 3.3 hop has no ``safe_overwrite`` entries still
       emerge with a populated ``tracked_files`` map.

    Skip-paths (``.agent/manifest.json``, ``.agent/sync-log.md``) are
    filtered out here so callers do not have to repeat the logic.
    """

    seen = []
    seen_set = set()

    def _add(rel):
        if not isinstance(rel, str) or not rel:
            return
        if rel in _TRACKED_FILES_SKIP_PATHS:
            return
        if rel in seen_set:
            return
        seen.append(rel)
        seen_set.add(rel)

    for entry in entries or []:
        if isinstance(entry, dict):
            _add(entry.get("target"))
    canonical = manifest.get("canonical_files") if isinstance(manifest, dict) else None
    for rel in canonical or []:
        _add(rel)
    return seen


def backfill_tracked_files(manifest, migration, target, entries, current_version):
    """One-shot backfill of ``manifest.tracked_files`` from on-disk bytes.

    Activation: only fires when the active migration opts in via
    ``manifest_updates.update_tracked_files: true``. The Stage 3.3
    1.0.0 migration is the first to set the flag; any prior migration
    is unaffected (no-op).

    Behavior is **purely additive**: for each path returned by
    :func:`collect_backfill_paths` that

      - exists on disk, AND
      - is NOT already recorded in ``manifest.tracked_files``,

    this records
    ``{synced_at_version: current_version,
       synced_checksum_sha256: sha256(disk_bytes)}``.

    The plan deliberately uses ``current_version`` (the manifest's
    pre-hop sync version) rather than the migration's ``to`` field
    because the disk bytes were authored against ``current``; using
    ``to`` would lie about provenance for files the current hop does
    not touch. The Stage 3.1 :func:`populate_tracked_files` writer
    runs immediately after this and overwrites entries for paths the
    hop *does* touch with ``synced_at_version=to`` plus the freshly
    written bytes' sha256, which is the correct provenance for those
    paths.

    Pre-existing ``tracked_files`` entries are **preserved untouched**
    — a 1.0.1+ hop that opts into ``update_tracked_files`` only seeds
    paths that were absent at 1.0.0 backfill time, so the recorded
    provenance of every legacy entry stays stable across hops. The
    refresh contract for entries the hop actually rewrites is the
    Stage 3.1 :func:`populate_tracked_files` writer's responsibility,
    not the backfill's.
    """

    if not should_update_tracked_files(migration):
        return manifest
    if not isinstance(current_version, str) or not current_version:
        return manifest

    existing = manifest.get(TRACKED_FILES_KEY)
    if isinstance(existing, dict):
        tracked = OrderedDict(existing)
    else:
        tracked = OrderedDict()

    for rel in collect_backfill_paths(entries, manifest):
        if rel in tracked:
            # Additive only: pre-existing record provenance wins. The
            # Stage 3.1 writer is the canonical refresher for entries
            # whose path the hop rewrites.
            continue
        path = target / rel
        try:
            data = path.read_bytes()
        except (FileNotFoundError, IsADirectoryError, OSError):
            continue
        tracked[rel] = compute_tracked_record(data, current_version)

    if tracked:
        manifest[TRACKED_FILES_KEY] = tracked
    return manifest


def apply_tracked_files_remove(manifest, migration):
    """Honor ``manifest_updates.tracked_files_remove: [<paths>]``.

    Schema v1's ``replace`` directive only upserts top-level scalars,
    so a migration that relocates or deletes a managed file cannot
    drop a stale entry under ``tracked_files`` via ``replace`` alone.
    This helper consumes a list of downstream-path strings and removes
    them from the map. Unknown / missing keys are silently skipped so
    the directive remains idempotent — re-running a migration that
    already removed its entries does not error.

    Activation is gated on the same ``update_tracked_files: true``
    opt-in flag as the writer to keep the surface coherent; emitting
    ``tracked_files_remove`` without ``update_tracked_files`` is a
    no-op (and a CI-time warning candidate for a future stage).
    """

    if not should_update_tracked_files(migration):
        return manifest

    updates = migration.get("manifest_updates") or {}
    removals = updates.get(TRACKED_FILES_REMOVE_KEY)
    if not isinstance(removals, list) or not removals:
        return manifest

    existing = manifest.get(TRACKED_FILES_KEY)
    if not isinstance(existing, dict):
        return manifest

    tracked = OrderedDict(existing)
    for rel in removals:
        if isinstance(rel, str) and rel in tracked:
            del tracked[rel]
    manifest[TRACKED_FILES_KEY] = tracked
    return manifest
