"""Tests for scripts/lib/validate_agent_system.py."""

from __future__ import annotations

import json
import os
import re
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

    def make_target(
        self,
        *,
        features: str = "standard",
        harness: str = "generic",
        install_hook: str | None = None,
        discover_gates: bool = False,
        prepopulate=None,
    ) -> Path:
        target = Path(tempfile.mkdtemp(prefix="agent-system-validator-"))
        self.addCleanup(lambda: shutil.rmtree(target, ignore_errors=True))
        if prepopulate is not None:
            prepopulate(target)
        args = [
            str(ROOT / "scripts" / "bootstrap-request.sh"),
            "--target",
            str(target),
            "--features",
            features,
            "--harness",
            harness,
        ]
        if install_hook == "bare":
            args.append("--install-hook")
        elif install_hook is not None:
            args.append(f"--install-hook={install_hook}")
        if discover_gates:
            args.append("--discover-gates")
        subprocess.run(
            args,
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
                "Nine optional native behavior skills",
                "Seven optional native behavior skills",
            ),
            encoding="utf-8",
        )

        result = self.run_validator("--mode", "template", "--format", "json", cwd=target)

        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        messages = "\n".join(item["message"] for item in payload["results"])
        self.assertIn("README.md has stale skill count mention(s): Seven optional native behavior skills", messages)

    def test_template_data_safety_skill_present_in_manifest_and_files(self):
        manifest = json.loads((ROOT / "core" / "skills" / "manifest.json").read_text(encoding="utf-8"))
        self.assertIn("data-safety", manifest["skills"])

        skill = (ROOT / "core" / "skills" / "data-safety" / "SKILL.md").read_text(encoding="utf-8")
        self.assertRegex(skill, r"(?m)^name: data-safety$")
        self.assertRegex(skill, r"(?m)^description: Use when")
        self.assertIn("## Canonical Sources", skill)

        mapping = (ROOT / "core" / "skills" / "README.md").read_text(encoding="utf-8")
        self.assertIn("| `data-safety` |", mapping)

    def test_template_data_safety_missing_from_manifest_fails(self):
        target = self.make_template_copy()
        manifest_path = target / "core" / "skills" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["skills"] = [skill for skill in manifest["skills"] if skill != "data-safety"]
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        result = self.run_validator("--mode", "template", "--format", "json", cwd=target)

        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        messages = "\n".join(item["message"] for item in payload["results"])
        self.assertIn("core/skills/manifest.json lists data-safety", messages)
        self.assertIn("core/skills contains skills not listed in manifest: data-safety", messages)

    def test_template_project_profile_template_missing_data_surface_fails(self):
        target = self.make_template_copy()
        profile = target / "core" / "project-profile.template.md"
        profile.write_text(
            profile.read_text(encoding="utf-8").replace("## Data Surface\n\n", "", 1),
            encoding="utf-8",
        )

        result = self.run_validator("--mode", "template", "--format", "json", cwd=target)

        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        messages = "\n".join(item["message"] for item in payload["results"])
        self.assertIn("core/project-profile.template.md includes Data Surface section", messages)

    def test_template_missing_adapter_tier_heading_fails(self):
        target = self.make_template_copy()
        path = target / "adapters" / "AGENTS.md"
        path.write_text(path.read_text(encoding="utf-8").replace("## Always do\n", "", 1), encoding="utf-8")
        result = self.run_validator("--mode", "template", "--format", "json", cwd=target)
        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        messages = "\n".join(item["message"] for item in payload["results"])
        self.assertIn("adapters/AGENTS.md includes ## Always do", messages)
        self.assertNotIn("Traceback", result.stderr)

    def test_generated_agents_md_includes_tier_headings(self):
        target = self.make_target()
        text = (target / "AGENTS.md").read_text(encoding="utf-8")
        for heading in ("## Always do", "## Ask first", "## Never do", "## Commands"):
            self.assertIn(heading, text)

    def test_generated_claude_adapters_include_tier_headings(self):
        target = self.make_target(harness="claude")
        for name in ("AGENTS.md", "CLAUDE.md"):
            text = (target / name).read_text(encoding="utf-8")
            for heading in ("## Always do", "## Ask first", "## Never do", "## Commands"):
                self.assertIn(heading, text)

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

    def test_bootstrap_implementer_subagent_includes_data_safety_skill(self):
        target = self.make_target(features="full", harness="claude")
        implementer = (target / ".claude" / "agents" / "implementer.md").read_text(encoding="utf-8")
        end = implementer.index("\n---\n", 4)
        frontmatter = implementer[4:end]
        self.assertRegex(frontmatter, r"(?m)^skills:.*\bdata-safety\b")
        self.assertIn("## Data Surface", (target / ".agent" / "project-profile.md").read_text(encoding="utf-8"))

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

    def test_install_hook_bare_stages_session_start_only(self):
        target = self.make_target(install_hook="bare")
        hooks_dir = target / ".agent" / "hooks"
        self.assertTrue((hooks_dir / "session-start.sh").is_file())
        self.assertFalse((hooks_dir / "pre-tool-use-secret-guard.py").exists())
        pending = (target / ".agent" / "bootstrap-pending.md").read_text(encoding="utf-8")
        self.assertIn("SessionStart hook: staged", pending)
        self.assertIn("PreToolUse secret-guard hook: not generated", pending)

    def test_install_hook_secret_guard_stages_secret_guard_only(self):
        target = self.make_target(install_hook="secret-guard")
        hooks_dir = target / ".agent" / "hooks"
        self.assertFalse((hooks_dir / "session-start.sh").exists())
        secret_hook = hooks_dir / "pre-tool-use-secret-guard.py"
        self.assertTrue(secret_hook.is_file())
        self.assertTrue(os.access(secret_hook, os.X_OK), "secret-guard hook must be executable")
        body = secret_hook.read_text(encoding="utf-8")
        self.assertTrue(body.startswith("#!/usr/bin/env python3"))
        self.assertIn("hookSpecificOutput", body)
        pending = (target / ".agent" / "bootstrap-pending.md").read_text(encoding="utf-8")
        self.assertIn("SessionStart hook: not generated", pending)
        self.assertIn("PreToolUse secret-guard hook: staged", pending)

    def test_install_hook_both_stages_both(self):
        target = self.make_target(install_hook="both")
        hooks_dir = target / ".agent" / "hooks"
        self.assertTrue((hooks_dir / "session-start.sh").is_file())
        self.assertTrue((hooks_dir / "pre-tool-use-secret-guard.py").is_file())
        pending = (target / ".agent" / "bootstrap-pending.md").read_text(encoding="utf-8")
        self.assertIn("SessionStart hook: staged", pending)
        self.assertIn("PreToolUse secret-guard hook: staged", pending)

    def test_bootstrap_without_discover_gates_keeps_marker_bodies_empty(self):
        target = self.make_target()
        eval_text = (target / "scripts" / "agent-eval.sh").read_text(encoding="utf-8")
        self.assertIn("# >>> AGENT-CANDIDATES gate=fast", eval_text)
        self.assertIn("# <<< END AGENT-CANDIDATES gate=fast", eval_text)
        # no candidate stub between any pair of markers
        import re

        for gate in (
            "changed",
            "fast",
            "frontend",
            "backend",
            "shared",
            "e2e",
            "full",
            "security",
            "release",
        ):
            block_re = re.compile(
                rf"# >>> AGENT-CANDIDATES gate={gate} — review before promoting <<<\n"
                rf"(?P<body>.*?)# <<< END AGENT-CANDIDATES gate={gate} <<<",
                re.DOTALL,
            )
            match = block_re.search(eval_text)
            self.assertIsNotNone(match, f"missing markers for gate={gate}")
            self.assertNotIn("#   run ", match.group("body"))
        manifest = json.loads((target / ".agent" / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("gate-candidate-discovery", manifest["features_enabled"])
        pending = (target / ".agent" / "bootstrap-pending.md").read_text(encoding="utf-8")
        self.assertIn("Gate candidate discovery: not run", pending)

    def test_bootstrap_with_discover_gates_inserts_node_candidate(self):
        def drop_package_json(target: Path) -> None:
            (target / "package.json").write_text(
                json.dumps(
                    {
                        "scripts": {
                            "test": "vitest run",
                            "lint": "eslint .",
                            "typecheck": "tsc --noEmit",
                        }
                    }
                ),
                encoding="utf-8",
            )

        target = self.make_target(discover_gates=True, prepopulate=drop_package_json)
        eval_text = (target / "scripts" / "agent-eval.sh").read_text(encoding="utf-8")
        self.assertIn("#   run npm run test", eval_text)
        self.assertIn("#   run npm run lint", eval_text)
        self.assertIn("#   run npm run typecheck", eval_text)
        self.assertRegex(
            eval_text,
            r"# source: package\.json::scripts\.test \(confidence=high\)",
        )
        # not_configured fallback must remain in the fast arm
        self.assertRegex(
            eval_text,
            r"(?ms)^\s*fast\)\n.*?not_configured",
        )

        manifest = json.loads((target / ".agent" / "manifest.json").read_text(encoding="utf-8"))
        self.assertIn("gate-candidate-discovery", manifest["features_enabled"])

        pending = (target / ".agent" / "bootstrap-pending.md").read_text(encoding="utf-8")
        self.assertIn("Gate candidate discovery: ran;", pending)

    def test_bootstrap_with_discover_gates_empty_target_omits_feature(self):
        target = self.make_target(discover_gates=True)
        eval_text = (target / "scripts" / "agent-eval.sh").read_text(encoding="utf-8")
        self.assertNotIn("#   run ", eval_text)

        manifest = json.loads((target / ".agent" / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("gate-candidate-discovery", manifest["features_enabled"])

        pending = (target / ".agent" / "bootstrap-pending.md").read_text(encoding="utf-8")
        self.assertIn("Gate candidate discovery: ran; no candidates discovered", pending)

        result = self.run_validator("--mode", "generated", "--format", "json", root=target)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["failure_count"], 0)

    def test_generated_validator_passes_with_discover_gates_feature(self):
        def drop_package_json(target: Path) -> None:
            (target / "package.json").write_text(
                json.dumps({"scripts": {"test": "vitest run"}}),
                encoding="utf-8",
            )

        target = self.make_target(discover_gates=True, prepopulate=drop_package_json)
        result = self.run_validator("--mode", "generated", "--format", "json", root=target)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["failure_count"], 0)
        messages = "\n".join(item["message"] for item in payload["results"])
        self.assertIn("contains discovered candidate stubs for gates", messages)

    def test_bootstrap_copies_audit_log_scripts(self):
        target = self.make_target()
        self.assertTrue((target / "scripts" / "agent-audit-log.sh").is_file())
        self.assertTrue(os.access(target / "scripts" / "agent-audit-log.sh", os.X_OK))
        self.assertTrue((target / "scripts" / "lib" / "audit_log.py").is_file())

    def test_bootstrap_does_not_modify_target_gitignore(self):
        def prepopulate_gitignore(target: Path) -> None:
            (target / ".gitignore").write_text("dist/\n.env\n", encoding="utf-8")

        target = self.make_target(prepopulate=prepopulate_gitignore)
        self.assertEqual((target / ".gitignore").read_text(encoding="utf-8"), "dist/\n.env\n")

    def test_agent_eval_trap_emits_gate_run(self):
        target = self.make_target()
        result = subprocess.run(
            ["bash", str(target / "scripts" / "agent-eval.sh"), "fast"],
            cwd=str(target),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        log_path = target / ".agent" / "audit-log.jsonl"
        self.assertTrue(log_path.is_file(), result.stdout + result.stderr)
        lines = log_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["kind"], "gate_run")
        self.assertEqual(record["gate"], "fast")
        self.assertEqual(record["exit_code"], 2)
        self.assertIsInstance(record["duration_ms"], int)

    def test_validate_plan_wrapper_preserves_stdout_byte_identical_under_github_format(self):
        target = self.make_target()
        plan_dir = target / ".agent" / "runs" / "bad-plan"
        plan_dir.mkdir(parents=True)
        (plan_dir / "plan.md").write_text("# Plan\n\n(missing required sections)\n", encoding="utf-8")

        wrapper = subprocess.run(
            [
                "bash",
                str(target / "scripts" / "agent-validate-plan.sh"),
                "--force",
                "--strict",
                "--format",
                "github",
                str(plan_dir),
            ],
            cwd=str(target),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        direct = subprocess.run(
            [
                sys.executable,
                str(target / "scripts" / "lib" / "validate_plan.py"),
                "--force",
                "--strict",
                "--format",
                "github",
                str(plan_dir),
            ],
            cwd=str(target),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(wrapper.returncode, direct.returncode)
        self.assertEqual(wrapper.stdout, direct.stdout)

    def test_validate_plan_audit_log_omits_counts_under_github_format(self):
        target = self.make_target()
        plan_dir = target / ".agent" / "runs" / "bad-plan"
        plan_dir.mkdir(parents=True)
        (plan_dir / "plan.md").write_text("# Plan\n\n(missing required sections)\n", encoding="utf-8")

        result = subprocess.run(
            [
                "bash",
                str(target / "scripts" / "agent-validate-plan.sh"),
                "--force",
                "--strict",
                "--format",
                "github",
                str(plan_dir),
            ],
            cwd=str(target),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        record = json.loads((target / ".agent" / "audit-log.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(record["kind"], "plan_validation")
        self.assertEqual(record["exit_code"], 1)
        self.assertNotIn("high", record)
        self.assertNotIn("medium", record)

    def test_validate_plan_audit_log_counts_under_human_format(self):
        target = self.make_target()
        plan_dir = target / ".agent" / "runs" / "bad-plan"
        plan_dir.mkdir(parents=True)
        (plan_dir / "plan.md").write_text("# Plan\n\n(missing required sections)\n", encoding="utf-8")

        result = subprocess.run(
            ["bash", str(target / "scripts" / "agent-validate-plan.sh"), "--force", "--strict", str(plan_dir)],
            cwd=str(target),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        summary = re.search(r"Summary: ([0-9]+) High, ([0-9]+) Medium", result.stdout)
        self.assertIsNotNone(summary, result.stdout)
        record = json.loads((target / ".agent" / "audit-log.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(record["kind"], "plan_validation")
        self.assertEqual(record["exit_code"], 1)
        self.assertEqual(record["high"], int(summary.group(1)))
        self.assertEqual(record["medium"], int(summary.group(2)))

    def test_install_hook_unknown_value_rejected(self):
        target = Path(tempfile.mkdtemp(prefix="agent-system-validator-"))
        self.addCleanup(lambda: shutil.rmtree(target, ignore_errors=True))
        result = subprocess.run(
            [
                str(ROOT / "scripts" / "bootstrap-request.sh"),
                "--target",
                str(target),
                "--install-hook=bogus",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown --install-hook value", result.stderr)
        self.assertFalse((target / ".agent").exists())


if __name__ == "__main__":
    unittest.main()
