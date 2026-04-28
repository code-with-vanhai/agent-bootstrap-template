#!/usr/bin/env python3
"""Validate Agent Bootstrap template-source or generated-repo structure."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


EXPECTED_GATE_MODES = ("changed", "fast", "frontend", "backend", "shared", "e2e", "full", "security", "release")
EXPECTED_COMMANDS = ("bootstrap", "plan", "bugfix", "implement", "refactor", "review", "security-review", "verify", "release-check")
EXPECTED_SKILLS = (
    "verify-before-completion",
    "root-cause-debugging",
    "scoped-implementation",
    "plan-before-code",
    "worktree-isolation",
    "no-invented-artifacts",
    "bootstrap-agent-system",
    "no-secret-leakage",
)
PLACEHOLDER_RE = re.compile(r"{{[A-Z][A-Z0-9_]*}}")


@dataclass
class Check:
    status: str
    message: str
    path: str | None = None


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def resolve_root(start: Path) -> tuple[Path, str]:
    env_root = os.environ.get("AGENT_ROOT")
    if env_root:
        return Path(env_root).resolve(), "env"
    if (start / ".agent").is_dir():
        return start.resolve(), "pwd"
    git = _run(["git", "rev-parse", "--show-toplevel"], start)
    if git.returncode == 0 and git.stdout.strip():
        return Path(git.stdout.strip()).resolve(), "git"
    return start.resolve(), "pwd"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


class AgentSystemValidator:
    def __init__(self, root: Path, mode: str):
        self.root = root
        self.mode = mode
        self.results: list[Check] = []

    def pass_(self, message: str, path: str | None = None) -> None:
        self.results.append(Check("PASS", message, path))

    def fail(self, message: str, path: str | None = None) -> None:
        self.results.append(Check("FAIL", message, path))

    def skip(self, message: str, path: str | None = None) -> None:
        self.results.append(Check("SKIP", message, path))

    def exists(self, rel: str) -> bool:
        if (self.root / rel).exists():
            self.pass_(f"{rel} exists", rel)
            return True
        self.fail(f"{rel} is missing", rel)
        return False

    def contains(self, rel: str, pattern: str, message: str, regex: bool = False) -> bool:
        path = self.root / rel
        if not path.is_file():
            self.fail(f"{message} cannot be checked because {rel} is missing", rel)
            return False
        text = read_text(path)
        ok = bool(re.search(pattern, text, re.MULTILINE)) if regex else pattern in text
        if ok:
            self.pass_(message, rel)
            return True
        self.fail(message, rel)
        return False

    def json_file(self, rel: str, message: str) -> dict[str, Any] | None:
        path = self.root / rel
        if not path.is_file():
            self.fail(f"{message} cannot be checked because {rel} is missing", rel)
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            self.fail(message, rel)
            return None
        self.pass_(message, rel)
        return data if isinstance(data, dict) else None

    def shell_syntax(self, rel: str) -> None:
        path = self.root / rel
        if not path.is_file():
            self.fail(f"{rel} shell syntax cannot be checked because file is missing", rel)
            return
        result = _run(["bash", "-n", rel], self.root)
        if result.returncode == 0:
            self.pass_(f"{rel} shell syntax is valid", rel)
        else:
            self.fail(f"{rel} shell syntax is invalid", rel)

    def py_compile(self, paths: Iterable[str], message: str) -> None:
        existing = [path for path in paths if (self.root / path).is_file()]
        if not existing:
            self.fail(f"{message} cannot be checked because no Python files were found")
            return
        result = _run([sys.executable, "-m", "py_compile", *existing], self.root)
        if result.returncode == 0:
            self.pass_(message)
        else:
            self.fail(message)

    def validate_command_files(self, command_root: str) -> None:
        for command in EXPECTED_COMMANDS:
            self.exists(f"{command_root}/{command}.md")
        self.contains(f"{command_root}/bootstrap.md", "agent-bootstrap --features standard --target .", f"{command_root}/bootstrap.md invokes plugin wrapper")
        self.contains(f"{command_root}/plan.md", "planning only", f"{command_root}/plan.md is phase-1 only")
        self.contains(f"{command_root}/bugfix.md", "bugfix-workflow.md", f"{command_root}/bugfix.md points to bugfix workflow")
        self.contains(f"{command_root}/implement.md", "implementation phase only", f"{command_root}/implement.md is implementation-phase only")
        self.contains(f"{command_root}/refactor.md", "refactor-workflow.md", f"{command_root}/refactor.md points to refactor workflow")
        self.contains(f"{command_root}/review.md", "review-workflow.md", f"{command_root}/review.md points to review workflow")
        self.contains(f"{command_root}/security-review.md", "security-review-workflow.md", f"{command_root}/security-review.md points to security review workflow")
        self.contains(f"{command_root}/verify.md", "scripts/agent-eval.sh <mode>", f"{command_root}/verify.md maps arguments to gate modes")
        self.contains(f"{command_root}/release-check.md", "release-check-workflow.md", f"{command_root}/release-check.md points to release-check workflow")

    def validate_gate_modes(self) -> None:
        for mode in EXPECTED_GATE_MODES:
            self.contains("core/manifest.template.json", f'"{mode}"', f"core/manifest.template.json includes {mode} gate mode")
            self.contains("core/commands/verify.md", f"`{mode}`", f"core/commands/verify.md includes {mode} gate mode")
            self.contains("scripts/agent-eval.template.sh", f"{mode})", f"scripts/agent-eval.template.sh includes {mode} gate mode")

    def validate_manifest_shape(self, rel: str) -> dict[str, Any] | None:
        data = self.json_file(rel, f"{rel} is valid JSON")
        if data is None:
            return None
        required = ("template_version", "canonical_root", "features_enabled", "project", "canonical_files", "verification", "tool_adapters", "notes")
        for key in required:
            if key in data:
                self.pass_(f"{rel} includes required field {key}", rel)
            else:
                self.fail(f"{rel} missing required field {key}", rel)
        if data.get("canonical_root") != ".agent":
            self.fail(f"{rel} canonical_root must be .agent", rel)
        verification = data.get("verification")
        if isinstance(verification, dict):
            if verification.get("entrypoint") == "scripts/agent-eval.sh":
                self.pass_(f"{rel} verification entrypoint is scripts/agent-eval.sh", rel)
            else:
                self.fail(f"{rel} verification entrypoint must be scripts/agent-eval.sh", rel)
            modes = verification.get("gate_modes")
            if isinstance(modes, list) and all(mode in modes for mode in EXPECTED_GATE_MODES):
                self.pass_(f"{rel} includes all expected gate modes", rel)
            else:
                self.fail(f"{rel} missing expected gate modes", rel)
        else:
            self.fail(f"{rel} verification must be an object", rel)
        if not isinstance(data.get("features_enabled"), list):
            self.fail(f"{rel} features_enabled must be an array", rel)
        project = data.get("project")
        if not isinstance(project, dict):
            self.fail(f"{rel} project must be an object", rel)
        adapters = data.get("tool_adapters")
        if not isinstance(adapters, dict) or not all(isinstance(value, str) for value in adapters.values()):
            self.fail(f"{rel} tool_adapters must map tool names to paths", rel)
        return data

    def validate_template(self) -> None:
        self.exists("core/bootstrap-steps.md")
        self.contains("core/bootstrap-steps.md", "Deterministic Skeleton", "core/bootstrap-steps.md includes deterministic skeleton phase")
        self.contains("core/bootstrap-steps.md", "Agent Completion", "core/bootstrap-steps.md includes agent completion phase")

        self.exists("scripts/bootstrap-request.sh")
        self.contains("scripts/bootstrap-request.sh", "--features", "scripts/bootstrap-request.sh supports feature selection")
        self.contains("scripts/bootstrap-request.sh", "--harness", "scripts/bootstrap-request.sh supports harness selection")
        self.contains("scripts/bootstrap-request.sh", "FEATURES_ENABLED_JSON_ARRAY", "scripts/bootstrap-request.sh renders feature metadata")
        self.shell_syntax("scripts/bootstrap-request.sh")

        self.exists("scripts/agent-validate.sh")
        self.shell_syntax("scripts/agent-validate.sh")
        self.contains("scripts/agent-validate.sh", "validate_agent_system.py", "scripts/agent-validate.sh invokes structured validator")
        self.exists("scripts/lib/validate_agent_system.py")
        self.py_compile(["scripts/lib/validate_agent_system.py"], "scripts/lib/validate_agent_system.py compiles")

        self.exists("scripts/agent-validate-plan.sh")
        self.shell_syntax("scripts/agent-validate-plan.sh")
        self.exists("scripts/agent-gate-discover.sh")
        self.shell_syntax("scripts/agent-gate-discover.sh")
        plan_validation_files = [str(path.relative_to(self.root)) for path in (self.root / "scripts/lib/plan_validation").glob("*.py")]
        self.exists("scripts/lib/validate_plan.py")
        self.exists("scripts/lib/plan_validation/cli.py")
        self.exists("scripts/lib/plan_validation/validator.py")
        self.py_compile(["scripts/lib/validate_plan.py", *plan_validation_files], "scripts/lib/validate_plan.py and plan_validation package compile")
        self.exists("scripts/lib/render_template.py")
        self.py_compile(["scripts/lib/render_template.py"], "scripts/lib/render_template.py compiles")
        self.exists("scripts/lib/gate_discovery.py")
        self.py_compile(["scripts/lib/gate_discovery.py"], "scripts/lib/gate_discovery.py compiles")

        self.exists("core/manifest.schema.json")
        self.json_file("core/manifest.schema.json", "core/manifest.schema.json is valid JSON")
        self.exists("core/manifest.template.json")
        self.contains("core/manifest.template.json", '"features_enabled"', "core/manifest.template.json includes features_enabled")
        self.contains("core/manifest.template.json", '"tool_adapters"', "core/manifest.template.json includes tool_adapters")
        self.contains("core/manifest.template.json", '"verification"', "core/manifest.template.json includes verification")

        self.exists(".claude-plugin/plugin.json")
        self.json_file(".claude-plugin/plugin.json", ".claude-plugin/plugin.json is valid JSON")
        self.contains(".claude-plugin/plugin.json", '"name": "agent-bootstrap"', ".claude-plugin/plugin.json defines agent-bootstrap plugin")
        self.contains(".claude-plugin/plugin.json", '"skills": "./core/skills/"', ".claude-plugin/plugin.json points to canonical skills")
        self.contains(".claude-plugin/plugin.json", '"commands": "./core/commands/"', ".claude-plugin/plugin.json points to canonical commands")

        self.exists("scripts/agent-eval.template.sh")
        self.contains("scripts/agent-eval.template.sh", "security)", "scripts/agent-eval.template.sh supports security gate mode")
        self.validate_gate_modes()

        self.exists(".claude-plugin/marketplace.json")
        self.json_file(".claude-plugin/marketplace.json", ".claude-plugin/marketplace.json is valid JSON")
        self.contains(".claude-plugin/marketplace.json", '"source": "./"', ".claude-plugin/marketplace.json installs plugin from repo root")

        if (self.root / "commands").is_dir():
            self.fail("root commands/ directory should not exist; use canonical core/commands/", "commands")
        else:
            self.pass_("root commands/ directory is absent", "commands")

        self.exists("core/command-conventions.md")
        self.contains("core/command-conventions.md", "Do not keep a second plugin-specific copy", "core/command-conventions.md includes drift rule")
        self.validate_command_files("core/commands")

        self.exists("bin/agent-bootstrap")
        self.contains("bin/agent-bootstrap", "--harness claude", "bin/agent-bootstrap defaults to Claude harness")
        self.shell_syntax("bin/agent-bootstrap")

        self.validate_github_metadata("core/github/PULL_REQUEST_TEMPLATE.md")
        self.exists("core/github/agent-template-ci.example.yml")
        self.contains("core/github/agent-template-ci.example.yml", "scripts/agent-validate.sh", "core/github/agent-template-ci.example.yml runs agent validation")
        self.contains("core/github/agent-template-ci.example.yml", "not configured", "core/github/agent-template-ci.example.yml handles not-configured fast gate")

        self.validate_worktree("core/workflows/worktree-workflow.md")
        self.exists("core/workflows/release-check-workflow.md")
        self.contains("core/workflows/release-check-workflow.md", "report-only", "core/workflows/release-check-workflow.md is report-only")
        self.contains("core/workflows/release-check-workflow.md", "Do not deploy", "core/workflows/release-check-workflow.md forbids deploy")

        self.exists("core/skills/README.md")
        self.contains("core/skills/README.md", "Skill Mapping", "core/skills/README.md includes skill mapping")
        skill_files = list((self.root / "core/skills").glob("*/SKILL.md"))
        if len(skill_files) == 8:
            self.pass_("core/skills contains 8 skill files", "core/skills")
        else:
            self.fail(f"core/skills contains {len(skill_files)} skill files, expected 8", "core/skills")
        for skill in EXPECTED_SKILLS:
            skill_file = f"core/skills/{skill}/SKILL.md"
            self.exists(skill_file)
            self.contains(skill_file, f"^name: {re.escape(skill)}$", f"{skill_file} has matching skill name", regex=True)
            self.contains(skill_file, "^description: Use when", f"{skill_file} has trigger-style description", regex=True)
            self.contains(skill_file, "Canonical Sources", f"{skill_file} lists canonical sources")
            self.contains("core/skills/README.md", f"`{skill}`", f"core/skills/README.md maps {skill}")

    def validate_github_metadata(self, rel: str) -> None:
        self.exists(rel)
        self.contains(rel, "Problem observed", f"{rel} includes problem observed section")
        self.contains(rel, "Gates run", f"{rel} includes gates run section")
        self.contains(rel, "fabricated problem statements, speculative fixes, or bundled unrelated changes", f"{rel} includes anti-slop warning")

    def validate_worktree(self, rel: str) -> None:
        self.exists(rel)
        self.contains(rel, "optional acceleration", f"{rel} states opt-in behavior")
        self.contains(rel, "Directory Priority", f"{rel} includes directory priority")
        self.contains(rel, "Baseline Gate", f"{rel} includes baseline gate")
        self.contains(rel, "When NOT To Use", f"{rel} includes when-not-to-use section")

    def manifest_has_feature(self, data: dict[str, Any] | None, feature: str) -> bool:
        return isinstance(data, dict) and feature in (data.get("features_enabled") or [])

    def check_placeholders(self) -> None:
        roots = [".agent", "AGENTS.md", "CLAUDE.md", "GEMINI.md", ".cursor", ".github", "scripts"]
        matches: list[str] = []
        for rel in roots:
            path = self.root / rel
            if path.is_file():
                files = [path]
            elif path.is_dir():
                files = [item for item in path.rglob("*") if item.is_file()]
            else:
                continue
            for item in files:
                text = read_text(item)
                if PLACEHOLDER_RE.search(text):
                    matches.append(item.relative_to(self.root).as_posix())
        if matches:
            self.fail("placeholders remain in generated agent files: " + ", ".join(matches[:5]))
        else:
            self.pass_("no template placeholders found")

    def validate_generated(self) -> None:
        if (self.root / ".agent").is_dir():
            self.check_placeholders()
            if not (self.root / ".agent/bootstrap-pending.md").is_file():
                marker_matches = []
                for rel in (".agent", "AGENTS.md", "CLAUDE.md", "GEMINI.md", ".cursor", ".github", "scripts"):
                    path = self.root / rel
                    files = [path] if path.is_file() else [item for item in path.rglob("*") if item.is_file()] if path.is_dir() else []
                    for item in files:
                        if "not confirmed - complete .agent/bootstrap-pending.md" in read_text(item):
                            marker_matches.append(item.relative_to(self.root).as_posix())
                if marker_matches:
                    self.fail("bootstrap completion markers remain after .agent/bootstrap-pending.md was removed")
                else:
                    self.pass_("no bootstrap completion markers remain")
            else:
                self.skip("bootstrap completion marker check while .agent/bootstrap-pending.md exists")
        else:
            self.fail(".agent directory is missing", ".agent")

        for rel in (
            ".agent/README.md",
            ".agent/manifest.json",
            ".agent/project-profile.md",
            ".agent/rulebase.md",
            ".agent/ownership.md",
            ".agent/gates.md",
            ".agent/decisions.md",
            ".agent/lessons.md",
            ".agent/roles/planner.md",
            ".agent/roles/implementer.md",
            ".agent/roles/reviewer.md",
            ".agent/roles/gate-runner.md",
            ".agent/roles/prompts/planner-subagent.md",
            ".agent/roles/prompts/implementer-subagent.md",
            ".agent/roles/prompts/reviewer-subagent.md",
            ".agent/roles/prompts/gate-runner-subagent.md",
            ".agent/workflows/bootstrap-workflow.md",
            ".agent/workflows/feature-workflow.md",
            ".agent/workflows/bugfix-workflow.md",
            ".agent/workflows/refactor-workflow.md",
            ".agent/workflows/review-workflow.md",
            ".agent/workflows/security-review-workflow.md",
            ".agent/workflows/improvement-cycle-workflow.md",
            ".agent/workflows/rule-evolution-workflow.md",
            "scripts/agent-eval.sh",
            "scripts/agent-gate-discover.sh",
            "scripts/lib/gate_discovery.py",
            "scripts/lib/validate_agent_system.py",
            "scripts/lib/validate_plan.py",
            "scripts/lib/plan_validation/cli.py",
            "scripts/lib/plan_validation/validator.py",
        ):
            self.exists(rel)

        self.contains(".agent/rulebase.md", "NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE", ".agent/rulebase.md includes completion verification discipline")
        self.contains(".agent/rulebase.md", "Rationalization Checks", ".agent/rulebase.md includes rationalization checks")
        self.contains(".agent/gates.md", "NO INVENTED GATES OR COMMANDS", ".agent/gates.md includes no-invented-gates discipline")

        manifest = self.validate_manifest_shape(".agent/manifest.json")

        self.shell_syntax("scripts/agent-eval.sh")
        self.shell_syntax("scripts/agent-gate-discover.sh")
        plan_validation_files = [str(path.relative_to(self.root)) for path in (self.root / "scripts/lib/plan_validation").glob("*.py")]
        self.py_compile(["scripts/lib/gate_discovery.py"], "scripts/lib/gate_discovery.py compiles")
        self.py_compile(["scripts/lib/validate_agent_system.py"], "scripts/lib/validate_agent_system.py compiles")
        self.py_compile(["scripts/lib/validate_plan.py", *plan_validation_files], "scripts/lib/validate_plan.py and plan_validation package compile")

        commands_enabled = (self.root / ".agent/commands").is_dir() or self.manifest_has_feature(manifest, "commands")
        if commands_enabled:
            self.exists(".agent/workflows/release-check-workflow.md")
            self.contains(".agent/gates.md", "scripts/agent-eval.sh <mode>", ".agent/gates.md documents gate mode signature")
            self.validate_command_files(".agent/commands")
        else:
            self.skip(".agent/commands not generated for this repo")
            if (self.root / ".agent/workflows/release-check-workflow.md").is_file():
                self.contains(".agent/workflows/release-check-workflow.md", "report-only", ".agent/workflows/release-check-workflow.md is report-only")
            else:
                self.skip(".agent/workflows/release-check-workflow.md not generated for this repo")

        for adapter in ("AGENTS.md", "CLAUDE.md", "GEMINI.md", ".cursor/rules/agent-system.mdc", ".github/copilot-instructions.md"):
            path = self.root / adapter
            if path.exists():
                if ".agent/" in read_text(path):
                    self.pass_(f"{adapter} points to .agent/", adapter)
                else:
                    self.fail(f"{adapter} exists but does not point to .agent/", adapter)
            else:
                self.skip(f"{adapter} not generated", adapter)

        if (self.root / ".github/PULL_REQUEST_TEMPLATE.md").is_file():
            self.validate_github_metadata(".github/PULL_REQUEST_TEMPLATE.md")
        else:
            self.skip(".github/PULL_REQUEST_TEMPLATE.md not generated", ".github/PULL_REQUEST_TEMPLATE.md")

        if (self.root / ".agent/workflows/worktree-workflow.md").is_file():
            self.validate_worktree(".agent/workflows/worktree-workflow.md")
        else:
            self.skip(".agent/workflows/worktree-workflow.md not generated", ".agent/workflows/worktree-workflow.md")

    def run(self) -> list[Check]:
        if self.mode == "template":
            self.validate_template()
        else:
            self.validate_generated()
        return self.results


def detect_mode(root: Path, requested: str) -> str:
    if requested != "auto":
        return requested
    if not (root / ".agent").is_dir() and (root / "core/skills").is_dir():
        return "template"
    return "generated"


def render_human(results: list[Check], mode: str) -> int:
    failures = [item for item in results if item.status == "FAIL"]
    for item in results:
        line = f"{item.status}: {item.message}"
        print(line, file=sys.stderr if item.status == "FAIL" else sys.stdout)
    if failures:
        noun = "template skill validation check(s)" if mode == "template" else "validation check(s)"
        print(f"\n{len(failures)} {noun} failed.", file=sys.stderr)
        return 1
    if mode == "template":
        print("\nAll template skill validation checks passed.")
    else:
        print("\nAll validation checks passed.")
    return 0


def render_github(results: list[Check]) -> int:
    failures = [item for item in results if item.status == "FAIL"]
    for item in failures:
        attrs = f" file={item.path}" if item.path else ""
        print(f"::error{attrs}::{item.message}")
    return 1 if failures else 0


def render_json(results: list[Check], root: Path, mode: str, root_source: str) -> int:
    failures = [item for item in results if item.status == "FAIL"]
    payload = {
        "root": str(root),
        "root_source": root_source,
        "mode": mode,
        "failure_count": len(failures),
        "results": [asdict(item) for item in results],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("template", "generated", "auto"), default="auto")
    parser.add_argument("--format", choices=("human", "github", "json"), default="human")
    args = parser.parse_args(argv)

    root, root_source = resolve_root(Path.cwd())
    mode = detect_mode(root, args.mode)
    if args.format == "human":
        print(f"Resolving root: {root} (source: {root_source})", file=sys.stderr)

    validator = AgentSystemValidator(root, mode)
    results = validator.run()

    if args.format == "github":
        return render_github(results)
    if args.format == "json":
        return render_json(results, root, mode, root_source)
    return render_human(results, mode)


if __name__ == "__main__":
    raise SystemExit(main())
