#!/usr/bin/env python3
"""Unit tests for the D-12 sync-log accepted-record format.

Locks down both formatters (single-hop and multi-hop) so a future
divergence between them is caught immediately, and exercises the
reader-side compatibility window that still parses legacy path-only
accepted lines from pre-0.12.0 logs.
"""

from __future__ import annotations

import sys
import unittest
from collections import OrderedDict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))

from agent_sync.merge import (  # noqa: E402
    AcceptedRecord,
    REASON_CATALOG_BASELINE_MATCH,
    REASON_USER_FLAG,
)
from agent_sync.sync_log import (  # noqa: E402
    multi_hop_sync_log_entry,
    parse_accepted_lines,
    restore_log_entry,
    sync_log_entry,
)


class AcceptedRecordRenderingTests(unittest.TestCase):
    def _migration(self):
        return OrderedDict(
            schema_version=1,
            version="0.8.0",
            **{"from": "0.7.0", "to": "0.8.0"},
        )

    def test_single_hop_renders_user_flag_record(self):
        record = AcceptedRecord(
            path="scripts/agent-eval.sh",
            reason=REASON_USER_FLAG,
            source="cli",
        )
        text = sync_log_entry(
            sync_now="2026-05-05T00:00:00Z",
            migration=self._migration(),
            template_commit="0123456789abcdef",
            updated=["scripts/agent-eval.sh"],
            accepted=[record],
            orphans=[],
            validation=["agent-validate: passed"],
        )
        self.assertIn(
            "  - scripts/agent-eval.sh [reason=user-flag, source=cli]",
            text,
        )
        accepted_block = text.split("- Accepted theirs:", 1)[1].split(
            "- Preserved:", 1
        )[0]
        self.assertNotIn(
            "  - scripts/agent-eval.sh\n",
            accepted_block,
            "accepted block must use D-12 format, not bare path",
        )

    def test_single_hop_renders_catalog_record(self):
        record = AcceptedRecord(
            path="scripts/agent-eval.sh",
            reason=REASON_CATALOG_BASELINE_MATCH,
            source="0.7.0->0.8.0 catalog",
        )
        text = sync_log_entry(
            sync_now="2026-05-05T00:00:00Z",
            migration=self._migration(),
            template_commit="0123456789abcdef",
            updated=["scripts/agent-eval.sh"],
            accepted=[record],
            orphans=[],
            validation=["agent-validate: passed"],
        )
        self.assertIn(
            "  - scripts/agent-eval.sh "
            "[reason=catalog-baseline-match, source=0.7.0->0.8.0 catalog]",
            text,
        )

    def test_multi_hop_renders_records_with_same_shape(self):
        record = AcceptedRecord(
            path="scripts/agent-eval.sh",
            reason=REASON_CATALOG_BASELINE_MATCH,
            source="0.7.0->0.8.0 catalog",
        )
        text = multi_hop_sync_log_entry(
            sync_now="2026-05-05T00:00:00Z",
            original_from="0.4.0",
            final_to="0.8.1",
            chain=["0.5.0", "0.6.0", "0.7.0", "0.8.0", "0.8.1"],
            template_commit="0123456789abcdef",
            updated=["scripts/agent-eval.sh"],
            accepted=[record],
            orphans=[],
            validation=["agent-validate: passed"],
        )
        self.assertIn(
            "  - scripts/agent-eval.sh "
            "[reason=catalog-baseline-match, source=0.7.0->0.8.0 catalog]",
            text,
        )

    def test_legacy_string_records_upgrade_to_user_flag(self):
        text = sync_log_entry(
            sync_now="2026-05-05T00:00:00Z",
            migration=self._migration(),
            template_commit="0123456789abcdef",
            updated=["scripts/agent-eval.sh"],
            accepted=["scripts/agent-eval.sh"],
            orphans=[],
            validation=["agent-validate: passed"],
        )
        self.assertIn(
            "  - scripts/agent-eval.sh [reason=user-flag, source=cli]",
            text,
        )

    def test_empty_accepted_keeps_none_marker(self):
        text = sync_log_entry(
            sync_now="2026-05-05T00:00:00Z",
            migration=self._migration(),
            template_commit="0123456789abcdef",
            updated=[],
            accepted=[],
            orphans=[],
            validation=[],
        )
        self.assertIn("- Accepted theirs:\n  - none", text)


class AcceptedReaderCompatTests(unittest.TestCase):
    def test_parses_d12_format(self):
        lines = [
            "  - scripts/agent-eval.sh [reason=user-flag, source=cli]",
            "  - core/foo.md [reason=catalog-baseline-match, source=0.7.0->0.8.0 catalog]",
        ]
        out = parse_accepted_lines(lines)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0].path, "scripts/agent-eval.sh")
        self.assertEqual(out[0].reason, "user-flag")
        self.assertEqual(out[0].source, "cli")
        self.assertEqual(out[1].reason, "catalog-baseline-match")

    def test_parses_legacy_path_only_format(self):
        lines = [
            "  - scripts/agent-eval.sh",
        ]
        out = parse_accepted_lines(lines)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].path, "scripts/agent-eval.sh")
        self.assertEqual(out[0].reason, "legacy")

    def test_parses_mixed_legacy_and_d12(self):
        lines = [
            "  - scripts/agent-eval.sh",
            "  - .agent/commands/foo.md [reason=user-flag, source=cli]",
        ]
        out = parse_accepted_lines(lines)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0].reason, "legacy")
        self.assertEqual(out[1].reason, "user-flag")


class RestoreLogEntryTests(unittest.TestCase):
    def test_shape(self):
        text = restore_log_entry(
            sync_now="2026-05-05T00:00:00Z",
            backup_id="2026-05-05T00-00-00Z-0.4.0-0.10.0",
            restored_from="0.4.0",
            file_count=42,
            backup_dir="/tmp/cache/abc/2026-05-05T00-00-00Z-0.4.0-0.10.0",
        )
        self.assertTrue(text.startswith("## "))
        self.assertIn("Restore 2026-05-05T00-00-00Z-0.4.0-0.10.0", text)
        self.assertIn("reverted 42 files to state at 0.4.0", text)


if __name__ == "__main__":
    unittest.main()
