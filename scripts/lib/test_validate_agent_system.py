"""Tests for scripts/lib/validate_agent_system.py."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts" / "lib" / "validate_agent_system.py"
WRAPPER = ROOT / "scripts" / "agent-validate.sh"


class AgentSystemValidatorTest(unittest.TestCase):
    def make_target(self, *, features: str = "standard", harness: str = "generic") -> Path:
        target = Path(tempfile.mkdtemp(prefix="agent-system-validator-"))
        self.addCleanup(lambda: shutil.rmtree(target, ignore_errors=True))
        subprocess.run(
            [
                str(ROOT / "scripts" / "bootstrap-request.sh"),
                "--target",
                str(target),
                "--features",
                features,
                "--harness",
                harness,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return target

    def complete_bootstrap_fixture(self, target: Path) -> None:
        marker = "not confirmed - complete .agent/bootstrap-pending.md"
        for root in (target / ".agent", target / "AGENTS.md", target / ".cursor", target / ".github"):
            if root.is_file():
                files = [root]
            elif root.is_dir():
                files = [item for item in root.rglob("*") if item.is_file()]
            else:
                continue
            for item in files:
                text = item.read_text(encoding="utf-8", errors="replace")
                if marker in text:
                    item.write_text(text.replace(marker, "confirmed by test fixture"), encoding="utf-8")
        pending = target / ".agent" / "bootstrap-pending.md"
        if pending.exists():
            pending.unlink()

    def run_validator(self, *args: str, cwd: Path = ROOT, root: Path | None = None):
        env = os.environ.copy()
        if root is not None:
            env["AGENT_ROOT"] = str(root)
        return subprocess.run(
            [sys.executable, str(VALIDATOR), *args],
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def test_template_json_mode_passes(self):
        result = self.run_validator("--mode", "template", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["mode"], "template")
        self.assertEqual(payload["failure_count"], 0)

    def test_generated_standard_passes_through_wrapper_with_agent_root(self):
        target = self.make_target()
        result = subprocess.run(
            ["bash", str(WRAPPER)],
            cwd=str(ROOT),
            env={**os.environ, "AGENT_ROOT": str(target)},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("All validation checks passed.", result.stdout)
        self.assertIn("source: env", result.stderr)

    def test_generated_full_codex_passes(self):
        target = self.make_target(features="full", harness="codex")
        result = self.run_validator("--mode", "generated", "--format", "json", root=target)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["mode"], "generated")
        self.assertEqual(payload["failure_count"], 0)

    def test_generated_post_bootstrap_ignores_validator_source_and_pycache(self):
        target = self.make_target()
        self.complete_bootstrap_fixture(target)
        subprocess.run(
            [sys.executable, "-m", "py_compile", str(target / "scripts/lib/validate_agent_system.py")],
            check=True,
        )

        result = self.run_validator("--mode", "generated", "--format", "json", root=target)

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["failure_count"], 0)

    def test_missing_adapter_pointer_fails_without_traceback(self):
        target = self.make_target()
        (target / "AGENTS.md").write_text("# Broken adapter\n", encoding="utf-8")
        result = subprocess.run(
            ["bash", str(target / "scripts" / "agent-validate.sh")],
            cwd=str(target),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        combined = result.stdout + result.stderr
        self.assertIn("AGENTS.md exists but does not point to .agent/", combined)
        self.assertIn("validation check(s) failed", combined)
        self.assertNotIn("Traceback", combined)

    def test_invalid_manifest_reports_validation_failures_as_json(self):
        target = self.make_target()
        (target / ".agent" / "manifest.json").write_text("{}", encoding="utf-8")
        result = self.run_validator("--mode", "generated", "--format", "json", root=target)
        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertGreater(payload["failure_count"], 0)
        messages = "\n".join(item["message"] for item in payload["results"])
        self.assertIn(".agent/manifest.json missing required field template_version", messages)
        self.assertNotIn("Traceback", result.stderr)

    def test_invalid_cli_value_exits_usage_2(self):
        result = self.run_validator("--mode", "invalid")
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)


if __name__ == "__main__":
    unittest.main()
