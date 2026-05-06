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
    UPDATE_TRACKED_FILES_FLAG,
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


if __name__ == "__main__":
    unittest.main()
