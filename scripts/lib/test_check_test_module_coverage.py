"""Tests for scripts/lib/check_test_module_coverage.py."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "lib" / "check_test_module_coverage.py"

# Import as a module to unit-test internals without spawning subprocess.
sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))
import check_test_module_coverage as checker  # noqa: E402


class ParseCiInvocationsTests(unittest.TestCase):
    def test_single_module_per_line(self) -> None:
        text = textwrap.dedent(
            """
            - name: tests
              run: |
                python3 -m unittest scripts.lib.test_a
                python3 -m unittest scripts.lib.test_b
            """
        )
        self.assertEqual(
            checker.parse_ci_invocations(text),
            {"scripts.lib.test_a", "scripts.lib.test_b"},
        )

    def test_multiple_modules_on_one_line(self) -> None:
        text = "python3 -m unittest scripts.lib.test_a scripts.lib.test_b"
        self.assertEqual(
            checker.parse_ci_invocations(text),
            {"scripts.lib.test_a", "scripts.lib.test_b"},
        )

    def test_ignores_flags_and_discover(self) -> None:
        text = "python3 -m unittest -v discover scripts.lib.test_a"
        self.assertEqual(
            checker.parse_ci_invocations(text),
            {"scripts.lib.test_a"},
        )

    def test_ignores_unrelated_modules(self) -> None:
        text = "python3 -m unittest other.test_x scripts.lib.test_a"
        self.assertEqual(
            checker.parse_ci_invocations(text),
            {"scripts.lib.test_a"},
        )


class CliBehaviorTests(unittest.TestCase):
    def _run(self, ci_yaml: str) -> subprocess.CompletedProcess:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".yml", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(ci_yaml)
            path = fh.name
        try:
            return subprocess.run(
                [sys.executable, str(SCRIPT), path],
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            pathlib.Path(path).unlink(missing_ok=True)

    def test_passes_when_all_modules_gated(self) -> None:
        on_disk = checker.discover_test_modules(REPO_ROOT / "scripts" / "lib")
        invocations = "\n".join(
            f"python3 -m unittest {mod}" for mod in sorted(on_disk)
        )
        result = self._run(f"run: |\n  {invocations}\n")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("PASS", result.stdout)

    def test_fails_when_module_missing_from_ci(self) -> None:
        on_disk = checker.discover_test_modules(REPO_ROOT / "scripts" / "lib")
        if len(on_disk) < 2:
            self.skipTest("need at least two modules to construct missing case")
        keep = sorted(on_disk)[:-1]
        invocations = "\n".join(f"python3 -m unittest {mod}" for mod in keep)
        result = self._run(f"run: |\n  {invocations}\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CI does not invoke", result.stderr)


if __name__ == "__main__":
    unittest.main()
