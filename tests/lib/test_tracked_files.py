#!/usr/bin/env python3
"""Unit tests for ``agent_sync.tracked_files`` (Stage 3.1).

Locks down two contracts:

1. **Default off, byte-stable.** Migrations that do NOT set
   ``manifest_updates.update_tracked_files: true`` must leave the
   manifest's ``tracked_files`` key untouched. This is the property
   that keeps every existing migration fixture green (notably
   ``tests/migrations/0.3.0/run.sh`` which asserts ``diff -r``
   tree-equality against a fixture without ``tracked_files``).
2. **Opt-in writer is correct.** When the flag is true, every path in
   the hop's ``writes`` dict (except the manifest itself and the
   sync-log) gets a record of shape
   ``{synced_at_version, synced_checksum_sha256}`` where the checksum
   is sha256 of the bytes about to be written.

Stage 3.2 (fast-path) and Stage 3.3 (1.0.0 backfill) build on this
writer; those are intentionally NOT exercised here so this slice stays
small, safe, and non-breaking.
"""

from __future__ import annotations

import hashlib
import sys
import unittest
from collections import OrderedDict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))

from agent_sync.tracked_files import (  # noqa: E402
    TRACKED_FILES_KEY,
    TRACKED_FILES_REMOVE_KEY,
    UPDATE_TRACKED_FILES_FLAG,
    apply_tracked_files_remove,
    backfill_tracked_files,
    collect_backfill_paths,
    compute_tracked_record,
    populate_tracked_files,
    should_update_tracked_files,
)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


class ShouldUpdateTrackedFilesTests(unittest.TestCase):
    def test_absent_flag_returns_false(self):
        self.assertFalse(should_update_tracked_files({}))
        self.assertFalse(
            should_update_tracked_files({"manifest_updates": {}})
        )

    def test_only_literal_true_activates(self):
        for value in (False, None, "true", 1, "yes"):
            with self.subTest(value=value):
                migration = {
                    "manifest_updates": {UPDATE_TRACKED_FILES_FLAG: value}
                }
                self.assertFalse(should_update_tracked_files(migration))

    def test_literal_true_activates(self):
        migration = {"manifest_updates": {UPDATE_TRACKED_FILES_FLAG: True}}
        self.assertTrue(should_update_tracked_files(migration))


class ComputeTrackedRecordTests(unittest.TestCase):
    def test_record_shape_and_hash(self):
        record = compute_tracked_record(b"hello\n", "1.0.0")
        self.assertEqual(record["synced_at_version"], "1.0.0")
        self.assertEqual(record["synced_checksum_sha256"], _sha(b"hello\n"))


class PopulateTrackedFilesTests(unittest.TestCase):
    def _migration(self, *, opt_in):
        updates = {}
        if opt_in:
            updates[UPDATE_TRACKED_FILES_FLAG] = True
        return {
            "schema_version": 1,
            "version": "1.0.0",
            "to": "1.0.0",
            "manifest_updates": updates,
        }

    def test_default_off_is_no_op(self):
        manifest = OrderedDict(template_version="0.11.0")
        out = populate_tracked_files(
            manifest,
            self._migration(opt_in=False),
            {".agent/rulebase.md": b"x"},
        )
        self.assertNotIn(TRACKED_FILES_KEY, out)

    def test_opt_in_populates_for_each_write(self):
        manifest = OrderedDict(template_version="0.11.0")
        writes = {
            ".agent/rulebase.md": b"# rulebase\n",
            "scripts/agent-eval.sh": b"#!/bin/sh\nfast() { :; }\n",
        }
        out = populate_tracked_files(
            manifest, self._migration(opt_in=True), writes
        )
        tracked = out[TRACKED_FILES_KEY]
        self.assertEqual(set(tracked.keys()), set(writes.keys()))
        for path, body in writes.items():
            self.assertEqual(tracked[path]["synced_at_version"], "1.0.0")
            self.assertEqual(
                tracked[path]["synced_checksum_sha256"], _sha(body)
            )

    def test_skip_paths_excluded(self):
        manifest = OrderedDict()
        writes = {
            ".agent/manifest.json": b"{}",
            ".agent/sync-log.md": b"# log\n",
            ".agent/rulebase.md": b"x",
        }
        out = populate_tracked_files(
            manifest, self._migration(opt_in=True), writes
        )
        self.assertEqual(
            list(out[TRACKED_FILES_KEY].keys()), [".agent/rulebase.md"]
        )

    def test_existing_entries_preserved_when_path_not_written(self):
        prior = OrderedDict(
            **{
                ".agent/old.md": OrderedDict(
                    synced_at_version="0.10.0",
                    synced_checksum_sha256=_sha(b"old"),
                )
            }
        )
        manifest = OrderedDict(tracked_files=prior)
        writes = {".agent/rulebase.md": b"new"}
        out = populate_tracked_files(
            manifest, self._migration(opt_in=True), writes
        )
        tracked = out[TRACKED_FILES_KEY]
        self.assertIn(".agent/old.md", tracked)
        self.assertEqual(
            tracked[".agent/old.md"]["synced_checksum_sha256"], _sha(b"old")
        )
        self.assertEqual(
            tracked[".agent/rulebase.md"]["synced_checksum_sha256"],
            _sha(b"new"),
        )

    def test_existing_entry_for_written_path_is_overwritten(self):
        prior = OrderedDict(
            **{
                ".agent/rulebase.md": OrderedDict(
                    synced_at_version="0.10.0",
                    synced_checksum_sha256=_sha(b"prev"),
                )
            }
        )
        manifest = OrderedDict(tracked_files=prior)
        writes = {".agent/rulebase.md": b"new"}
        out = populate_tracked_files(
            manifest, self._migration(opt_in=True), writes
        )
        tracked = out[TRACKED_FILES_KEY]
        self.assertEqual(tracked[".agent/rulebase.md"]["synced_at_version"], "1.0.0")
        self.assertEqual(
            tracked[".agent/rulebase.md"]["synced_checksum_sha256"],
            _sha(b"new"),
        )

    def test_empty_writes_is_no_op_even_when_opted_in(self):
        manifest = OrderedDict()
        out = populate_tracked_files(
            manifest, self._migration(opt_in=True), {}
        )
        self.assertNotIn(TRACKED_FILES_KEY, out)

    def test_missing_to_version_short_circuits(self):
        migration = {
            "manifest_updates": {UPDATE_TRACKED_FILES_FLAG: True},
            "to": None,
        }
        manifest = OrderedDict()
        out = populate_tracked_files(manifest, migration, {".agent/x": b"y"})
        self.assertNotIn(TRACKED_FILES_KEY, out)

    def test_non_bytes_value_in_writes_is_ignored(self):
        manifest = OrderedDict()
        writes = {
            ".agent/string-write.md": "should be ignored",
            ".agent/bytes-write.md": b"counts",
        }
        out = populate_tracked_files(
            manifest, self._migration(opt_in=True), writes
        )
        tracked = out[TRACKED_FILES_KEY]
        self.assertEqual(
            list(tracked.keys()), [".agent/bytes-write.md"]
        )


class PlanManifestIntegrationTests(unittest.TestCase):
    """Smoke test the wire-up inside ``manifest_ops.plan_manifest``.

    This is the boundary layer that would regress the AC-2 fixture
    invariants if the opt-in branch ever started firing for legacy
    migrations. Lock both directions: opt-out leaves manifest output
    byte-identical to today; opt-in produces a queued write whose JSON
    contains the new ``tracked_files`` key.
    """

    def setUp(self):
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target = Path(self.tmp.name)
        (self.target / ".agent").mkdir()
        manifest_path = self.target / ".agent" / "manifest.json"
        manifest_path.write_text(
            '{\n  "instantiated_from_template_version": "0.11.0"\n}\n',
            encoding="utf-8",
        )

    def _read_manifest(self):
        from agent_sync.io_utils import read_json

        return read_json(self.target / ".agent" / "manifest.json")

    def _plan(self, migration, writes_in):
        from agent_sync.manifest_ops import plan_manifest

        manifest = self._read_manifest()
        writes = dict(writes_in)
        updated = []
        plan_manifest(
            template_root=Path("."),
            target=self.target,
            migration=migration,
            manifest=manifest,
            sync_now="2026-05-05T00:00:00Z",
            writes=writes,
            updated=updated,
        )
        return writes, updated

    def test_legacy_migration_does_not_emit_tracked_files(self):
        migration = {
            "schema_version": 1,
            "version": "0.11.0",
            "to": "0.11.0",
            "manifest_updates": {
                "replace": {"template_version": "0.11.0"},
            },
        }
        writes, _ = self._plan(migration, {".agent/rulebase.md": b"x"})
        manifest_bytes = writes[".agent/manifest.json"]
        self.assertNotIn(b'"tracked_files"', manifest_bytes)

    def test_opt_in_migration_writes_tracked_files_key(self):
        migration = {
            "schema_version": 1,
            "version": "1.0.0",
            "to": "1.0.0",
            "manifest_updates": {
                "replace": {"template_version": "1.0.0"},
                UPDATE_TRACKED_FILES_FLAG: True,
            },
        }
        writes, _ = self._plan(
            migration,
            {
                ".agent/rulebase.md": b"# rulebase\n",
            },
        )
        self.assertIn(".agent/manifest.json", writes)
        manifest_bytes = writes[".agent/manifest.json"]
        self.assertIn(b'"tracked_files"', manifest_bytes)
        import json

        parsed = json.loads(manifest_bytes.decode("utf-8"))
        self.assertIn(".agent/rulebase.md", parsed["tracked_files"])
        self.assertEqual(
            parsed["tracked_files"][".agent/rulebase.md"][
                "synced_at_version"
            ],
            "1.0.0",
        )
        self.assertEqual(
            parsed["tracked_files"][".agent/rulebase.md"][
                "synced_checksum_sha256"
            ],
            _sha(b"# rulebase\n"),
        )


class CollectBackfillPathsTests(unittest.TestCase):
    """``collect_backfill_paths`` is the de-duplicated source for both the
    Stage 3.3 backfill helper and any future preflight that wants to
    quote the same scope. Locks down ordering and the skip-paths
    filter.
    """

    def _entry(self, target):
        return {"source": target, "target": target, "kind": "safe_overwrite"}

    def test_entries_listed_first_canonical_appended(self):
        manifest = {"canonical_files": [".agent/rulebase.md", ".agent/gates.md"]}
        entries = [self._entry(".agent/constitution.md"), self._entry(".agent/rulebase.md")]
        paths = collect_backfill_paths(entries, manifest)
        # Entry order preserved; canonical appended for items not already seen.
        self.assertEqual(
            paths,
            [".agent/constitution.md", ".agent/rulebase.md", ".agent/gates.md"],
        )

    def test_skip_paths_filtered(self):
        manifest = {"canonical_files": [".agent/manifest.json", ".agent/gates.md"]}
        entries = [
            self._entry(".agent/sync-log.md"),
            self._entry(".agent/rulebase.md"),
        ]
        paths = collect_backfill_paths(entries, manifest)
        self.assertEqual(paths, [".agent/rulebase.md", ".agent/gates.md"])

    def test_handles_missing_inputs_safely(self):
        self.assertEqual(collect_backfill_paths(None, None), [])
        self.assertEqual(collect_backfill_paths([], {}), [])
        self.assertEqual(collect_backfill_paths([{}], {"canonical_files": [123]}), [])


class BackfillTrackedFilesTests(unittest.TestCase):
    """One-shot backfill semantics (Stage 3.3 / D-7).

    Locks down five contracts:

    1. Default-off when the migration does not opt in.
    2. Records ``synced_at_version=current``, NOT ``to``.
    3. Files absent on disk are skipped (no fabricated entries).
    4. Pre-existing entries for paths outside the backfill scope are
       preserved verbatim.
    5. Combined with :func:`populate_tracked_files`, paths the hop
       writes get refreshed to ``synced_at_version=to``.
    """

    def setUp(self):
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target = Path(self.tmp.name)

    def _write(self, rel, body):
        path = self.target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return body

    def _migration(self, *, opt_in, to="1.0.0"):
        updates = {}
        if opt_in:
            updates[UPDATE_TRACKED_FILES_FLAG] = True
        return {
            "schema_version": 1,
            "version": to,
            "to": to,
            "manifest_updates": updates,
        }

    def test_default_off_no_op(self):
        body = self._write(".agent/rulebase.md", b"# rb\n")
        manifest = OrderedDict(canonical_files=[".agent/rulebase.md"])
        out = backfill_tracked_files(
            manifest,
            self._migration(opt_in=False),
            self.target,
            entries=[],
            current_version="0.11.0",
        )
        self.assertNotIn(TRACKED_FILES_KEY, out)
        # Sanity check we actually had the byte to hash had backfill fired.
        self.assertEqual(_sha(body), _sha(b"# rb\n"))

    def test_records_synced_at_version_as_current_not_to(self):
        body = self._write(".agent/rulebase.md", b"# disk bytes\n")
        manifest = OrderedDict(canonical_files=[".agent/rulebase.md"])
        out = backfill_tracked_files(
            manifest,
            self._migration(opt_in=True, to="1.0.0"),
            self.target,
            entries=[],
            current_version="0.11.0",
        )
        record = out[TRACKED_FILES_KEY][".agent/rulebase.md"]
        self.assertEqual(record["synced_at_version"], "0.11.0")
        self.assertEqual(record["synced_checksum_sha256"], _sha(body))

    def test_missing_disk_file_is_skipped(self):
        manifest = OrderedDict(
            canonical_files=[".agent/rulebase.md", ".agent/never-created.md"]
        )
        body = self._write(".agent/rulebase.md", b"only this one\n")
        out = backfill_tracked_files(
            manifest,
            self._migration(opt_in=True),
            self.target,
            entries=[],
            current_version="0.11.0",
        )
        tracked = out[TRACKED_FILES_KEY]
        self.assertEqual(list(tracked.keys()), [".agent/rulebase.md"])
        self.assertEqual(
            tracked[".agent/rulebase.md"]["synced_checksum_sha256"], _sha(body)
        )

    def test_preserves_existing_entries_outside_scope(self):
        prior = OrderedDict(
            **{
                ".agent/external.md": OrderedDict(
                    synced_at_version="0.5.0",
                    synced_checksum_sha256=_sha(b"pre-existing"),
                )
            }
        )
        manifest = OrderedDict(
            tracked_files=prior, canonical_files=[".agent/rulebase.md"]
        )
        body = self._write(".agent/rulebase.md", b"# rb\n")
        out = backfill_tracked_files(
            manifest,
            self._migration(opt_in=True),
            self.target,
            entries=[],
            current_version="0.11.0",
        )
        tracked = out[TRACKED_FILES_KEY]
        self.assertIn(".agent/external.md", tracked)
        self.assertEqual(
            tracked[".agent/external.md"]["synced_at_version"], "0.5.0"
        )
        self.assertEqual(
            tracked[".agent/rulebase.md"]["synced_checksum_sha256"], _sha(body)
        )

    def test_existing_entry_for_in_scope_path_is_preserved(self):
        """Backfill is purely additive: an entry already present must
        keep its provenance (synced_at_version + checksum) even when
        its path is part of the backfill scope. The Stage 3.1 writer
        is the only path that may legitimately refresh entries for
        paths the hop actually rewrites; the backfill must not.
        """

        prior_record = OrderedDict(
            synced_at_version="0.11.0",
            synced_checksum_sha256=_sha(b"backfilled-at-1.0.0"),
        )
        manifest = OrderedDict(
            tracked_files=OrderedDict(**{".agent/rulebase.md": prior_record}),
            canonical_files=[".agent/rulebase.md", ".agent/gates.md"],
        )
        # New disk bytes for rulebase (post-customization) — backfill
        # should still NOT overwrite the prior entry. gates.md is new
        # to the map and exists on disk, so it must be seeded.
        self._write(".agent/rulebase.md", b"# user-edited rulebase\n")
        gates_body = self._write(".agent/gates.md", b"# gates\n")
        out = backfill_tracked_files(
            manifest,
            self._migration(opt_in=True, to="1.0.1"),
            self.target,
            entries=[],
            current_version="1.0.0",
        )
        tracked = out[TRACKED_FILES_KEY]
        # Pre-existing rulebase entry untouched.
        self.assertEqual(
            tracked[".agent/rulebase.md"]["synced_at_version"], "0.11.0"
        )
        self.assertEqual(
            tracked[".agent/rulebase.md"]["synced_checksum_sha256"],
            _sha(b"backfilled-at-1.0.0"),
        )
        # New gates.md entry seeded with the current hop's source version.
        self.assertEqual(
            tracked[".agent/gates.md"]["synced_at_version"], "1.0.0"
        )
        self.assertEqual(
            tracked[".agent/gates.md"]["synced_checksum_sha256"],
            _sha(gates_body),
        )

    def test_populate_overwrites_backfill_entry_for_touched_path(self):
        """Stage 3.1 + 3.3 wire-up: backfill seeds ``current``, then
        populate_tracked_files refreshes touched paths to ``to``.
        """

        body_disk = self._write(".agent/rulebase.md", b"# disk bytes\n")
        manifest = OrderedDict(canonical_files=[".agent/rulebase.md"])
        migration = self._migration(opt_in=True, to="1.0.0")

        manifest = backfill_tracked_files(
            manifest, migration, self.target, [], "0.11.0"
        )
        self.assertEqual(
            manifest[TRACKED_FILES_KEY][".agent/rulebase.md"][
                "synced_at_version"
            ],
            "0.11.0",
        )

        new_bytes = b"# new bytes\n"
        manifest = populate_tracked_files(
            manifest, migration, {".agent/rulebase.md": new_bytes}
        )
        record = manifest[TRACKED_FILES_KEY][".agent/rulebase.md"]
        self.assertEqual(record["synced_at_version"], "1.0.0")
        self.assertEqual(record["synced_checksum_sha256"], _sha(new_bytes))
        # Backfill's seeded sha is replaced; we did NOT keep the disk
        # bytes' sha after the writer ran.
        self.assertNotEqual(record["synced_checksum_sha256"], _sha(body_disk))


class ApplyTrackedFilesRemoveTests(unittest.TestCase):
    """``manifest_updates.tracked_files_remove`` directive.

    Locks the same opt-in gate as the writer (so a migration that
    accidentally turns the writer off cannot keep removing entries),
    plus idempotent skip semantics.
    """

    def _migration(self, *, opt_in, removals):
        updates = {}
        if opt_in:
            updates[UPDATE_TRACKED_FILES_FLAG] = True
        if removals is not None:
            updates[TRACKED_FILES_REMOVE_KEY] = removals
        return {"schema_version": 1, "to": "1.0.1", "manifest_updates": updates}

    def _manifest(self):
        return OrderedDict(
            tracked_files=OrderedDict(
                **{
                    ".agent/keep.md": OrderedDict(
                        synced_at_version="1.0.0",
                        synced_checksum_sha256=_sha(b"keep"),
                    ),
                    ".agent/old.md": OrderedDict(
                        synced_at_version="1.0.0",
                        synced_checksum_sha256=_sha(b"old"),
                    ),
                }
            )
        )

    def test_default_off_no_removal(self):
        manifest = self._manifest()
        out = apply_tracked_files_remove(
            manifest,
            self._migration(opt_in=False, removals=[".agent/old.md"]),
        )
        self.assertIn(".agent/old.md", out[TRACKED_FILES_KEY])

    def test_opt_in_removes_listed_keys(self):
        manifest = self._manifest()
        out = apply_tracked_files_remove(
            manifest,
            self._migration(opt_in=True, removals=[".agent/old.md"]),
        )
        tracked = out[TRACKED_FILES_KEY]
        self.assertNotIn(".agent/old.md", tracked)
        self.assertIn(".agent/keep.md", tracked)

    def test_unknown_keys_idempotent(self):
        manifest = self._manifest()
        out = apply_tracked_files_remove(
            manifest,
            self._migration(opt_in=True, removals=[".agent/never-tracked.md"]),
        )
        self.assertEqual(
            list(out[TRACKED_FILES_KEY].keys()),
            [".agent/keep.md", ".agent/old.md"],
        )

    def test_no_directive_no_op(self):
        manifest = self._manifest()
        out = apply_tracked_files_remove(
            manifest, self._migration(opt_in=True, removals=None)
        )
        self.assertEqual(
            list(out[TRACKED_FILES_KEY].keys()),
            [".agent/keep.md", ".agent/old.md"],
        )

    def test_non_string_entries_silently_skipped(self):
        manifest = self._manifest()
        out = apply_tracked_files_remove(
            manifest,
            self._migration(opt_in=True, removals=[None, 42, ".agent/old.md"]),
        )
        self.assertNotIn(".agent/old.md", out[TRACKED_FILES_KEY])
        self.assertIn(".agent/keep.md", out[TRACKED_FILES_KEY])


if __name__ == "__main__":
    unittest.main()
