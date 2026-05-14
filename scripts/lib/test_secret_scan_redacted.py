"""Tests for scripts/lib/secret_scan_redacted.py."""

from __future__ import annotations

import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.lib import secret_scan_redacted as scanner


class SecretScanRedactedTests(unittest.TestCase):
    def make_root(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="secret-scan-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def fake_aws_key(self) -> str:
        return "AKIA" + "IOSFODNN7EXAMPLE"

    def test_clean_directory_returns_no_findings(self) -> None:
        root = self.make_root()
        (root / "README.md").write_text("hello\n", encoding="utf-8")

        self.assertEqual(scanner.scan(root), [])

    def test_aws_key_is_detected_without_printing_value(self) -> None:
        root = self.make_root()
        secret = self.fake_aws_key()
        (root / "leaked.py").write_text(
            'API_KEY = "' + secret + '"\n', encoding="utf-8"
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = scanner.main(["--root", str(root)])

        self.assertEqual(rc, 1)
        output = stdout.getvalue()
        self.assertIn("FINDING: leaked.py:1 [AWS_ACCESS_KEY_ID]", output)
        self.assertNotIn(secret, output)

    def test_env_dot_production_files_are_scanned(self) -> None:
        root = self.make_root()
        (root / ".env.production").write_text(
            "SECRET=" + ("a" * 40) + "\n", encoding="utf-8"
        )

        findings = scanner.scan(root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, ".env.production")

    def test_symlinks_are_skipped(self) -> None:
        root = self.make_root()
        outside = self.make_root()
        real = outside / "real.txt"
        real.write_text("not secret\n", encoding="utf-8")
        link = root / "linked.txt"
        link.symlink_to(real)
        real.write_text("token=" + ("b" * 40) + "\n", encoding="utf-8")

        self.assertEqual(scanner.scan(root), [])

    def test_large_files_are_skipped(self) -> None:
        root = self.make_root()
        large = root / "large.txt"
        large.write_text(
            ("x" * (scanner.MAX_FILE_BYTES + 1))
            + "\nAPI_KEY="
            + self.fake_aws_key()
            + "\n",
            encoding="utf-8",
        )

        self.assertEqual(scanner.scan(root), [])

    def test_excluded_directories_are_skipped(self) -> None:
        root = self.make_root()
        excluded = root / "node_modules"
        excluded.mkdir()
        (excluded / "leak.js").write_text(
            "token=" + ("c" * 40) + "\n", encoding="utf-8"
        )

        self.assertEqual(scanner.scan(root), [])

    def test_allow_marker_suppresses_only_that_line(self) -> None:
        root = self.make_root()
        secret = self.fake_aws_key()
        (root / "fixture.txt").write_text(
            "token=" + ("d" * 40) + " # agent-secret-scan:allow\n"
            + 'key = "'
            + secret
            + '"\n',
            encoding="utf-8",
        )

        findings = scanner.scan(root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].pattern, "AWS_ACCESS_KEY_ID")


if __name__ == "__main__":
    unittest.main()
