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
    def make_template_copy(self) -> Path:
        parent = Path(tempfile.mkdtemp(prefix="agent-template-validator-"))
        self.addCleanup(lambda: shutil.rmtree(parent, ignore_errors=True))
        target = parent / "repo"
        shutil.copytree(
            ROOT,
            target,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
        )
        return target

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

    def test_template_missing_skill_manifest_fails(self):
        target = self.make_template_copy()
        (target / "core/skills/manifest.json").unlink()

        result = self.run_validator("--mode", "template", "--format", "json", cwd=target)

        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        messages = "\n".join(item["message"] for item in payload["results"])
        self.assertIn("core/skills/manifest.json is valid JSON cannot be checked", messages)
        self.assertNotIn("Traceback", result.stderr)

    def test_template_manifest_skill_missing_directory_fails(self):
        target = self.make_template_copy()
        shutil.rmtree(target / "core/skills/no-secret-leakage")

        result = self.run_validator("--mode", "template", "--format", "json", cwd=target)

        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        messages = "\n".join(item["message"] for item in payload["results"])
        self.assertIn("core/skills missing manifest skill directories: no-secret-leakage", messages)

    def test_template_unexpected_skill_directory_fails(self):
        target = self.make_template_copy()
        extra = target / "core/skills/extra-skill"
        extra.mkdir()
        (extra / "SKILL.md").write_text(
            "---\nname: extra-skill\ndescription: Use when testing extra skills.\n---\n\n# Extra\n\n## Canonical Sources\n\n- `.agent/rulebase.md`\n",
            encoding="utf-8",
        )

        result = self.run_validator("--mode", "template", "--format", "json", cwd=target)

        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        messages = "\n".join(item["message"] for item in payload["results"])
        self.assertIn("core/skills contains skills not listed in manifest: extra-skill", messages)

    def test_template_stale_skill_count_doc_fails(self):
        target = self.make_template_copy()
        readme = target / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8").replace(
                "Eight optional native behavior skills",
                "Seven optional native behavior skills",
            ),
            encoding="utf-8",
        )

        result = self.run_validator("--mode", "template", "--format", "json", cwd=target)

        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        messages = "\n".join(item["message"] for item in payload["results"])
        self.assertIn("README.md has stale skill count mention(s): Seven optional native behavior skills", messages)

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
        manifest = json.loads((target / ".agent" / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("claude-native-subagents", manifest["features_enabled"])
        self.assertFalse((target / ".claude" / "agents").exists())

    def test_generated_full_claude_subagents_passes(self):
        target = self.make_target(features="full", harness="claude")
        result = self.run_validator("--mode", "generated", "--format", "json", root=target)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["mode"], "generated")
        self.assertEqual(payload["failure_count"], 0)

        manifest = json.loads((target / ".agent" / "manifest.json").read_text(encoding="utf-8"))
        self.assertIn("claude-native-subagents", manifest["features_enabled"])

        agents_dir = target / ".claude" / "agents"
        expected = {"planner.md", "implementer.md", "reviewer.md", "gate-runner.md"}
        actual = {p.name for p in agents_dir.iterdir() if p.is_file()}
        self.assertEqual(actual, expected)

        for filename in expected:
            body = (agents_dir / filename).read_text(encoding="utf-8")
            self.assertTrue(body.startswith("---\n"), f"{filename} missing frontmatter start")
            try:
                end = body.index("\n---\n", 4)
            except ValueError:
                self.fail(f"{filename} missing frontmatter terminator")
            frontmatter = body[4:end]
            for field in ("name:", "description:", "tools:", "permissionMode:", "maxTurns:", "skills:"):
                self.assertIn(field, frontmatter, f"{filename} frontmatter missing {field}")
            self.assertNotRegex(frontmatter, r"(?m)^model:", f"{filename} must not pin model")
            self.assertIn("Subagent Prompt", body[end:])

    def test_generated_full_claude_planner_disallows_writes(self):
        target = self.make_target(features="full", harness="claude")
        planner = (target / ".claude" / "agents" / "planner.md").read_text(encoding="utf-8")
        end = planner.index("\n---\n", 4)
        frontmatter = planner[4:end]
        self.assertRegex(frontmatter, r"(?m)^tools:.*\bBash\b")
        self.assertRegex(frontmatter, r"(?m)^disallowedTools:.*Edit.*Write.*MultiEdit")
        self.assertRegex(frontmatter, r"(?m)^permissionMode:\s+plan\s*$")

    def test_generated_full_claude_implementer_omits_disallowed_tools(self):
        target = self.make_target(features="full", harness="claude")
        implementer = (target / ".claude" / "agents" / "implementer.md").read_text(encoding="utf-8")
        end = implementer.index("\n---\n", 4)
        frontmatter = implementer[4:end]
        self.assertRegex(frontmatter, r"(?m)^tools:.*Edit.*Write.*MultiEdit")
        self.assertNotRegex(frontmatter, r"(?m)^disallowedTools:")

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
