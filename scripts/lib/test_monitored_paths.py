"""Tests for incremental validation monitored paths."""

from __future__ import annotations

import ast
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.lib.agent_system_validation import monitored_paths


ROOT = Path(__file__).resolve().parents[2]


class MonitoredPathsTests(unittest.TestCase):
    def make_repo(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="monitored-paths-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=root,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=root,
            check=True,
        )
        (root / "README.md").write_text("base\n", encoding="utf-8")
        (root / "scripts").mkdir()
        (root / "scripts" / "agent-eval.sh").write_text(
            "base\n", encoding="utf-8"
        )
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=root, check=True)
        (root / "README.md").write_text("head\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "head"], cwd=root, check=True)
        return root

    def exists_paths_from_generated_checker(self) -> set[str]:
        source = (
            ROOT
            / "scripts"
            / "lib"
            / "agent_system_validation"
            / "checks_generated.py"
        )
        tree = ast.parse(source.read_text(encoding="utf-8"))
        found: set[str] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "validator"
                and func.attr == "exists"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                found.add(node.args[0].value)
        return found

    def test_generated_validator_paths_are_monitored(self) -> None:
        monitored = set(monitored_paths.MONITORED_PATHS_FOR_INCREMENTAL)
        missing = self.exists_paths_from_generated_checker() - monitored
        self.assertEqual(missing, set())

    def test_diff_quiet_exit_code_zero_for_unmonitored_change(self) -> None:
        root = self.make_repo()
        (root / "README.md").write_text("worktree\n", encoding="utf-8")

        self.assertEqual(monitored_paths.diff_quiet(root, "HEAD~1"), 0)

    def test_diff_quiet_exit_code_one_for_monitored_change(self) -> None:
        root = self.make_repo()
        (root / "scripts" / "agent-eval.sh").write_text(
            "changed\n", encoding="utf-8"
        )

        self.assertEqual(monitored_paths.diff_quiet(root, "HEAD~1"), 1)

    def test_diff_quiet_exit_code_greater_than_one_for_git_error(self) -> None:
        root = self.make_repo()

        self.assertGreater(monitored_paths.diff_quiet(root, "missing-ref"), 1)

    def test_module_cli_diff_quiet(self) -> None:
        root = self.make_repo()
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.lib.agent_system_validation.monitored_paths",
                "diff-quiet",
                "--root",
                str(root),
                "--base",
                "HEAD~1",
            ],
            cwd=ROOT,
        )

        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
