"""Tests for Stage 2.1 ``bump_version`` helper."""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
LIB = REPO_ROOT / "scripts" / "lib"
sys.path.insert(0, str(LIB))

import bump_version as bv  # noqa: E402
import check_version_consistency as vercheck  # noqa: E402


def _make_fixture(root: pathlib.Path, version: str) -> None:
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "bootstrap-request.sh").write_text(
        f'#!/usr/bin/env bash\ntemplate_version="{version}"\n', encoding="utf-8"
    )
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"version": version}), encoding="utf-8"
    )
    (root / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(
            {
                "metadata": {"version": version},
                "plugins": [
                    {"name": "agent-bootstrap", "version": version},
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## {version} - 2026-01-01\n\n- entry\n",
        encoding="utf-8",
    )


class BumpVersionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tags = REPO_ROOT / "core" / "release-tags.md"

    def test_bump_updates_five_sources_and_adds_pending_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _make_fixture(root, "1.0.0")
            (root / "core").mkdir()
            shutil.copyfile(self._tags, root / "core" / "release-tags.md")

            self.assertTrue(bv.bump(root, "1.0.1", "2026-05-05"))

            self.assertEqual(vercheck.extract_bootstrap_version(root), "1.0.1")
            self.assertEqual(vercheck.extract_plugin_version(root), "1.0.1")
            mm, mp = vercheck.extract_marketplace_versions(root)
            self.assertEqual(mm, "1.0.1")
            self.assertEqual(mp, "1.0.1")
            self.assertEqual(vercheck.extract_changelog_version(root), "1.0.1")

            text = (root / "core" / "release-tags.md").read_text(encoding="utf-8")
            self.assertIn("1.0.1", text)
            self.assertIn("<PENDING>", text)

            self.assertEqual(vercheck.report(list(vercheck.collect(root))), 0)
            err, _msg = vercheck.strict_release_tags_pending(root)
            self.assertEqual(err, 1)

    def test_bump_preserves_executable_bit_on_bootstrap_script(self) -> None:
        """Regression: ``_atomic_write`` must preserve file mode.

        ``tempfile.mkstemp`` creates files at mode 0600 by default; the
        previous implementation silently stripped the 0755 bit from
        ``scripts/bootstrap-request.sh`` on every bump, which broke the
        downstream bootstrap (Permission denied at exec time).
        """
        import os
        import stat

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _make_fixture(root, "1.0.0")
            (root / "core").mkdir()
            shutil.copyfile(self._tags, root / "core" / "release-tags.md")
            script = root / "scripts" / "bootstrap-request.sh"
            os.chmod(script, 0o755)
            self.assertTrue(bv.bump(root, "1.1.0", "2026-05-06"))
            mode_after = stat.S_IMODE(script.stat().st_mode)
            self.assertEqual(
                mode_after,
                0o755,
                msg=f"executable bit stripped: mode={oct(mode_after)}",
            )

    def test_idempotent_noop_when_already_at_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _make_fixture(root, "2.0.0")
            (root / "core").mkdir()
            shutil.copyfile(self._tags, root / "core" / "release-tags.md")
            self.assertFalse(bv.bump(root, "2.0.0", "2026-05-05"))

    def test_cli_strict_fails_with_pending_row_after_bump(self) -> None:
        """Plan AC-8: ``--strict`` must exit non-zero with a ``<PENDING>``
        marker in stderr after a bump, until the annotated-tag SHA is
        backfilled. Asserts both the exit code AND the error shape via
        subprocess so a regression that silently returns 0 is caught.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _make_fixture(root, "1.0.0")
            (root / "core").mkdir()
            shutil.copyfile(self._tags, root / "core" / "release-tags.md")
            self.assertTrue(bv.bump(root, "1.0.1", "2026-05-05"))

            proc = subprocess.run(
                [
                    sys.executable,
                    str(LIB / "check_version_consistency.py"),
                    "--root",
                    str(root),
                    "--strict",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(
                proc.returncode,
                0,
                msg=f"strict should fail with pending row; stdout={proc.stdout!r} stderr={proc.stderr!r}",
            )
            self.assertIn("<PENDING>", proc.stderr)
            self.assertIn("1.0.1", proc.stderr)

    def test_promotes_unreleased_section_preserving_prose(self) -> None:
        """When CHANGELOG has ``## Unreleased``, the bump promotes that
        heading in place rather than inserting a fresh empty block.

        The hand-written prose under Unreleased becomes the body of the
        new release; no duplicate heading appears, no empty bullet
        sentinel is left behind.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _make_fixture(root, "1.0.0")
            (root / "core").mkdir()
            shutil.copyfile(self._tags, root / "core" / "release-tags.md")
            (root / "CHANGELOG.md").write_text(
                "# Changelog\n\n"
                "## Unreleased\n\n"
                "- Hand-written prose describing the next release.\n"
                "- Another bullet with detail.\n\n"
                "## 1.0.0 - 2026-01-01\n\n- entry\n",
                encoding="utf-8",
            )
            self.assertTrue(bv.bump(root, "1.1.0", "2026-05-06"))
            text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
            self.assertIn("## 1.1.0 - 2026-05-06", text)
            self.assertNotIn("## Unreleased", text)
            self.assertIn("Hand-written prose describing the next release.", text)
            self.assertIn("Another bullet with detail.", text)
            # Old release section preserved verbatim.
            self.assertIn("## 1.0.0 - 2026-01-01", text)
            # No empty placeholder bullet from legacy insert path.
            self.assertNotIn("\n## 1.1.0 - 2026-05-06\n\n- \n\n", text)
            # Heading appears exactly once.
            self.assertEqual(text.count("## 1.1.0 - 2026-05-06"), 1)
            # Blank line between heading and first bullet must be preserved
            # (regression guard: greedy ``\s*`` would swallow the newline).
            self.assertIn(
                "## 1.1.0 - 2026-05-06\n\n- Hand-written prose", text
            )
            # Version-consistency check still passes.
            self.assertEqual(vercheck.report(list(vercheck.collect(root))), 0)

    def test_unreleased_promotion_case_insensitive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _make_fixture(root, "1.0.0")
            (root / "core").mkdir()
            shutil.copyfile(self._tags, root / "core" / "release-tags.md")
            (root / "CHANGELOG.md").write_text(
                "# Changelog\n\n## UNRELEASED\n\n- Existing prose.\n\n"
                "## 1.0.0 - 2026-01-01\n\n- entry\n",
                encoding="utf-8",
            )
            self.assertTrue(bv.bump(root, "1.0.1", "2026-05-06"))
            text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
            self.assertIn("## 1.0.1 - 2026-05-06", text)
            self.assertNotIn("UNRELEASED", text)
            self.assertIn("Existing prose.", text)

    def test_cli_strict_passes_on_real_repo(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(LIB / "check_version_consistency.py"), "--strict"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr + proc.stdout)


if __name__ == "__main__":
    unittest.main()
