"""``manifest.tracked_files`` schema helpers (Stage 3.1).

This module owns the schema and the post-plan writer for the
``tracked_files`` map introduced by Stage 3.1 of
``docs/2026-05-05-migration-ux-improvement-plan.md``. It intentionally
lives in its own file rather than inside :mod:`manifest_ops` so the
fast-path / backfill follow-ups (Stage 3.2 / 3.3) can extend the schema
without bloating manifest write planning.

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

The runner only populates ``tracked_files`` when the active migration's
``manifest_updates`` block sets ``update_tracked_files: true``. No
existing migration JSON sets that flag, so this slice is strictly
opt-in: legacy migrations and fixtures (e.g. ``tests/migrations/0.3.0/
after/.agent/manifest.json``) keep their byte-exact post-apply state
because nothing ever adds the ``tracked_files`` key.

Stage 3.2 (fast-path) and Stage 3.3 (one-shot 1.0.0 backfill) build on
this writer; they are intentionally not implemented here so the slice
stays small, safe, and non-breaking.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict


TRACKED_FILES_KEY = "tracked_files"
UPDATE_TRACKED_FILES_FLAG = "update_tracked_files"

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
