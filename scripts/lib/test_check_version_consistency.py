"""Tests for scripts/lib/check_version_consistency.py."""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "lib" / "check_version_consistency.py"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))
import check_version_consistency as checker  # noqa: E402


def _make_fixture(tmp: pathlib.Path, version: str) -> None:
    (tmp / "scripts").mkdir()
    (tmp / "scripts" / "bootstrap-request.sh").write_text(
        f'#!/usr/bin/env bash\ntemplate_version="{version}"\n', encoding="utf-8"
    )
    (tmp / ".claude-plugin").mkdir()
    (tmp / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"version": version}), encoding="utf-8"
    )
    (tmp / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(
            {
                "metadata": {"version": version},
                "plugins": [
                    {"name": "agent-bootstrap", "version": version},
                    {"name": "other", "version": "9.9.9"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## {version} - 2026-01-01\n\n- entry\n",
        encoding="utf-8",
    )


class ExtractorTests(unittest.TestCase):
    def test_all_sources_extracted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _make_fixture(root, "1.2.3")
            self.assertEqual(checker.extract_bootstrap_version(root), "1.2.3")
            self.assertEqual(checker.extract_plugin_version(root), "1.2.3")
            self.assertEqual(
                checker.extract_marketplace_versions(root), ("1.2.3", "1.2.3")
            )
            self.assertEqual(checker.extract_changelog_version(root), "1.2.3")

    def test_changelog_picks_topmost_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _make_fixture(root, "1.2.3")
            (root / "CHANGELOG.md").write_text(
                "# Changelog\n\n"
                "## 1.2.3 - 2026-01-02\n- newest\n\n"
                "## 1.2.2 - 2025-12-01\n- older\n",
                encoding="utf-8",
            )
            self.assertEqual(checker.extract_changelog_version(root), "1.2.3")


class CliReportTests(unittest.TestCase):
    def _run(self, root: pathlib.Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root)],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_passes_when_all_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _make_fixture(root, "1.2.3")
            result = self._run(root)
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("PASS", result.stdout)

    def test_fails_when_skewed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _make_fixture(root, "1.2.3")
            plugin_json = root / ".claude-plugin" / "plugin.json"
            plugin_json.write_text(
                json.dumps({"version": "1.2.4"}), encoding="utf-8"
            )
            result = self._run(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("version skew", result.stderr)

    def test_fails_when_non_semver(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _make_fixture(root, "v1.2.3")
            result = self._run(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("non-semver", result.stderr)

    def test_repo_passes(self) -> None:
        # Sanity: this repo's own version sources must agree.
        result = self._run(REPO_ROOT)
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_strict_fails_when_changelog_row_missing(self) -> None:
        """``--strict`` must refuse to pass when the CHANGELOG's latest
        release has no row in ``core/release-tags.md`` — closes the
        Stage 1+2 review gap where deleting the 0.11.0 row still passed
        strict because the check only looked at the newest row's
        ``<PENDING>`` marker.
        """

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _make_fixture(root, "1.2.3")
            (root / "core").mkdir()
            # release-tags.md lists a DIFFERENT (older) version, so the
            # CHANGELOG's 1.2.3 has no matching row.
            (root / "core" / "release-tags.md").write_text(
                "# Release Tags\n\n"
                "| Version | Tag | Commit | Notes |\n"
                "|---------|-----|--------|-------|\n"
                "| 1.2.2 | `v1.2.2` | `deadbeefcafebabe0123456789abcdef01234567` | older release. |\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root), "--strict"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("1.2.3", result.stderr)
            self.assertIn("release-tags.md", result.stderr)


if __name__ == "__main__":
    unittest.main()
