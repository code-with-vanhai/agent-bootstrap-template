"""Planner-skip parity for :func:`preflight.classify_merge_mode`.

When ``enabled_when_path_exists`` fails or ``skip_if_target_missing`` skips
because the downstream file is absent, ``merge.plan_safe_overwrites`` does
not process the row. Preflight merge-mode counts MUST exclude those rows
(stage-3 feedback: avoid over-counting optional entries).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.lib.agent_sync.preflight import classify_merge_mode


class ClassifyMergeModeSkipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.target = base / "downstream"
        self.target.mkdir()
        self.template_root = base / "template"
        self.template_root.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    @patch("scripts.lib.agent_sync.preflight.tag_exists", return_value=True)
    def test_none_when_skip_if_target_missing_and_file_absent(self, _mock):
        entry = {
            "source": "adapters/CLAUDE.md",
            "target": "CLAUDE.md",
            "skip_if_target_missing": True,
        }
        self.assertFalse((self.target / "CLAUDE.md").exists())
        self.assertIsNone(
            classify_merge_mode(
                entry,
                self.target,
                self.template_root,
                "0.9.0",
                "1.0.0",
                {},
            )
        )

    @patch("scripts.lib.agent_sync.preflight.tag_exists", return_value=True)
    def test_modes_when_skip_if_target_missing_but_file_present(self, _mock):
        (self.target / "CLAUDE.md").write_text("# user\n", encoding="utf-8")
        entry = {
            "source": "adapters/CLAUDE.md",
            "target": "CLAUDE.md",
            "skip_if_target_missing": True,
        }
        mode = classify_merge_mode(
            entry,
            self.target,
            self.template_root,
            "0.9.0",
            "1.0.0",
            {},
        )
        self.assertEqual(mode, "3-way-merge")

    @patch("scripts.lib.agent_sync.preflight.tag_exists", return_value=True)
    def test_none_when_enabled_when_path_exists_missing(self, _mock):
        entry = {
            "source": "core/skills/x/SKILL.md",
            "target": ".agents/x/SKILL.md",
            "enabled_when_path_exists": ".agents/skills/agent-bootstrap",
        }
        mode = classify_merge_mode(
            entry,
            self.target,
            self.template_root,
            "0.9.0",
            "1.0.0",
            {},
        )
        self.assertIsNone(mode)

    @patch("scripts.lib.agent_sync.preflight.tag_exists", return_value=True)
    def test_classifies_when_enabled_when_path_exists_present(self, _mock):
        anchor = ".agents/skills/agent-bootstrap"
        (self.target / anchor).mkdir(parents=True)
        entry = {
            "source": "core/skills/x/SKILL.md",
            "target": ".agents/x/SKILL.md",
            "enabled_when_path_exists": anchor,
        }
        mode = classify_merge_mode(
            entry,
            self.target,
            self.template_root,
            "0.9.0",
            "1.0.0",
            {},
        )
        self.assertEqual(mode, "3-way-merge")


if __name__ == "__main__":
    unittest.main()
