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
SKILL_COUNT_WORDS = {
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
WORD_SKILL_COUNT_RE = re.compile(
    r"\b(seven|eight|nine|ten|eleven|twelve)\s+"
    r"(optional\s+)?(native\s+)?(behavior\s+)?skills?\b",
    re.IGNORECASE,
)
NUMERIC_SKILL_COUNT_RE = re.compile(
    r"\b(\d+)\s+(optional\s+)?(native\s+)?(behavior\s+)?skills?\b",
    re.IGNORECASE,
)
PLACEHOLDER_RE = re.compile(r"{{[A-Z][A-Z0-9_]*}}")
GENERATED_TEXT_ROOTS = (".agent", "AGENTS.md", "CLAUDE.md", "GEMINI.md", ".cursor", ".github")
GENERATED_SCAN_EXCLUDED_DIRS = {"__pycache__"}
GENERATED_SCAN_EXCLUDED_SUFFIXES = {".pyc"}
# Excluding bytecode is the load-bearing defense here: Python const-folds
# adjacent string literals and stores the joined value in .pyc files.
BOOTSTRAP_COMPLETION_MARKER = "not confirmed - complete " + ".agent/bootstrap-pending.md"


THIN_ADAPTER_SOURCE_FILES = (
    "adapters/AGENTS.md",
    "adapters/CLAUDE.md",
    "adapters/GEMINI.md",
    "adapters/cursor-agent-system.mdc",
    "adapters/copilot-instructions.md",
)
THIN_ADAPTER_GENERATED_PATHS = (
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".cursor/rules/agent-system.mdc",
    ".github/copilot-instructions.md",
)
THIN_ADAPTER_TIER_HEADINGS = (
    "## Always do",
    "## Ask first",
    "## Never do",
    "## Commands",
)

GATE_CANDIDATE_MARKER_OPEN_FMT = "# >>> AGENT-CANDIDATES gate={gate} — review before promoting <<<"
GATE_CANDIDATE_MARKER_CLOSE_FMT = "# <<< END AGENT-CANDIDATES gate={gate} <<<"
GATE_CANDIDATE_RUN_RE = re.compile(r"^\s*#\s+run\s+\S", re.MULTILINE)


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


def parse_skill_mapping_names(text: str) -> set[str]:
    names: set[str] = set()
    in_mapping = False
    for line in text.splitlines():
        if line.strip() == "## Skill Mapping":
            in_mapping = True
            continue
        if in_mapping and line.startswith("## "):
            break
        if not in_mapping or not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or cells[0].lower() in {"skill", "---"}:
            continue
        if set(cells[0]) <= {"-", " "}:
            continue
        match = re.fullmatch(r"`([^`]+)`", cells[0])
        if match:
            names.add(match.group(1))
    return names


def skill_count_mentions(text: str) -> list[tuple[str, int]]:
    mentions: list[tuple[str, int]] = []
    for match in WORD_SKILL_COUNT_RE.finditer(text):
        mentions.append((match.group(0), SKILL_COUNT_WORDS[match.group(1).lower()]))
    for match in NUMERIC_SKILL_COUNT_RE.finditer(text):
        mentions.append((match.group(0), int(match.group(1))))
    return mentions


def generated_text_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for rel in GENERATED_TEXT_ROOTS:
        path = root / rel
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(
                item
                for item in path.rglob("*")
                if item.is_file()
                and not GENERATED_SCAN_EXCLUDED_DIRS.intersection(item.parts)
                and item.suffix not in GENERATED_SCAN_EXCLUDED_SUFFIXES
            )
    return files


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

    def load_skill_manifest(self) -> list[str]:
        rel = "core/skills/manifest.json"
        data = self.json_file(rel, f"{rel} is valid JSON")
        if data is None:
            return []
        if data.get("schema_version") == 1:
            self.pass_(f"{rel} schema_version is 1", rel)
        else:
            self.fail(f"{rel} schema_version must be 1", rel)

        skills = data.get("skills")
        if not isinstance(skills, list) or not skills or not all(isinstance(item, str) for item in skills):
            self.fail(f"{rel} skills must be a non-empty array of strings", rel)
            return []

        duplicates = sorted({item for item in skills if skills.count(item) > 1})
        if duplicates:
            self.fail(f"{rel} contains duplicate skill names: {', '.join(duplicates)}", rel)
        else:
            self.pass_(f"{rel} lists {len(skills)} skills", rel)
        return skills

    def validate_skill_set(self, skills: list[str]) -> None:
        expected = set(skills)
        actual = {
            path.parent.name
            for path in (self.root / "core/skills").glob("*/SKILL.md")
        }
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        if missing:
            self.fail("core/skills missing manifest skill directories: " + ", ".join(missing), "core/skills")
        if unexpected:
            self.fail("core/skills contains skills not listed in manifest: " + ", ".join(unexpected), "core/skills")
        if not missing and not unexpected:
            self.pass_(f"core/skills matches manifest skill set ({len(expected)} skills)", "core/skills")

        for skill in skills:
            skill_file = f"core/skills/{skill}/SKILL.md"
            self.exists(skill_file)
            self.contains(skill_file, f"^name: {re.escape(skill)}$", f"{skill_file} has matching skill name", regex=True)
            self.contains(skill_file, "^description: Use when", f"{skill_file} has trigger-style description", regex=True)
            self.contains(skill_file, "Canonical Sources", f"{skill_file} lists canonical sources")

    def validate_skill_mapping(self, skills: list[str]) -> None:
        rel = "core/skills/README.md"
        path = self.root / rel
        if not path.is_file():
            self.fail(f"{rel} Skill Mapping cannot be checked because file is missing", rel)
            return
        mapped = parse_skill_mapping_names(read_text(path))
        expected = set(skills)
        missing = sorted(expected - mapped)
        unexpected = sorted(mapped - expected)
        if missing:
            self.fail(f"{rel} Skill Mapping is missing skills: {', '.join(missing)}", rel)
        if unexpected:
            self.fail(f"{rel} Skill Mapping lists unexpected skills: {', '.join(unexpected)}", rel)
        if not missing and not unexpected:
            self.pass_(f"{rel} Skill Mapping matches manifest skill set", rel)

    def validate_skill_count_docs(self, skills: list[str]) -> None:
        expected_count = len(skills)
        for rel in ("README.md", "USAGE.md", "core/skills/README.md"):
            path = self.root / rel
            if not path.is_file():
                self.skip(f"{rel} not present for skill count drift check", rel)
                continue
            mismatches = [
                phrase
                for phrase, count in skill_count_mentions(read_text(path))
                if count != expected_count
            ]
            if mismatches:
                self.fail(
                    f"{rel} has stale skill count mention(s): {', '.join(mismatches)}; "
                    f"expected {expected_count} skills from core/skills/manifest.json",
                    rel,
                )
            else:
                self.pass_(f"{rel} skill count mentions match manifest", rel)

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
        self.exists("scripts/lib/insert_gate_candidates.py")
        self.py_compile(["scripts/lib/insert_gate_candidates.py"], "scripts/lib/insert_gate_candidates.py compiles")

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
        self.validate_gate_candidate_markers_template()

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
        skills = self.load_skill_manifest()
        if skills:
            self.validate_skill_set(skills)
            self.validate_skill_mapping(skills)
            self.validate_skill_count_docs(skills)

        self.validate_hook_templates()
        for rel in THIN_ADAPTER_SOURCE_FILES:
            self.validate_thin_adapter_file(rel)

    def validate_thin_adapter_file(self, rel: str) -> None:
        if not (self.root / rel).is_file():
            self.fail(f"{rel} is missing", rel)
            return
        text = read_text(self.root / rel)
        if ".agent/" in text:
            self.pass_(f"{rel} points to .agent/", rel)
        else:
            self.fail(f"{rel} exists but does not point to .agent/", rel)
        for heading in THIN_ADAPTER_TIER_HEADINGS:
            self.contains(rel, heading, f"{rel} includes {heading}")

    def validate_gate_candidate_markers_template(self) -> None:
        rel = "scripts/agent-eval.template.sh"
        if not (self.root / rel).is_file():
            self.fail(f"{rel} is missing", rel)
            return
        text = read_text(self.root / rel)
        for gate in EXPECTED_GATE_MODES:
            open_marker = GATE_CANDIDATE_MARKER_OPEN_FMT.format(gate=gate)
            close_marker = GATE_CANDIDATE_MARKER_CLOSE_FMT.format(gate=gate)
            if open_marker in text and close_marker in text:
                self.pass_(f"{rel} includes AGENT-CANDIDATES marker pair for gate={gate}", rel)
            else:
                missing = "open" if open_marker not in text else "close"
                self.fail(
                    f"{rel} missing AGENT-CANDIDATES {missing} marker for gate={gate}",
                    rel,
                )

    def validate_gate_candidate_markers_generated(
        self, manifest: dict[str, Any] | None
    ) -> None:
        rel = "scripts/agent-eval.sh"
        path = self.root / rel
        if not path.is_file():
            self.skip(f"{rel} missing; gate-candidate marker checks skipped", rel)
            return
        text = read_text(path)
        all_markers_present = True
        gate_segments: dict[str, str] = {}
        for gate in EXPECTED_GATE_MODES:
            open_marker = GATE_CANDIDATE_MARKER_OPEN_FMT.format(gate=gate)
            close_marker = GATE_CANDIDATE_MARKER_CLOSE_FMT.format(gate=gate)
            try:
                start = text.index(open_marker)
                end = text.index(close_marker, start + len(open_marker))
            except ValueError:
                missing = "open" if open_marker not in text else "close"
                self.fail(
                    f"{rel} missing AGENT-CANDIDATES {missing} marker for gate={gate}",
                    rel,
                )
                all_markers_present = False
                continue
            gate_segments[gate] = text[start + len(open_marker) : end]
            self.pass_(f"{rel} includes AGENT-CANDIDATES marker pair for gate={gate}", rel)

        if not all_markers_present:
            return

        if self.manifest_has_feature(manifest, "gate-candidate-discovery"):
            populated = [
                gate
                for gate, segment in gate_segments.items()
                if GATE_CANDIDATE_RUN_RE.search(segment)
            ]
            if populated:
                self.pass_(
                    f"{rel} contains discovered candidate stubs for gates: "
                    f"{', '.join(populated)}",
                    rel,
                )
            else:
                self.fail(
                    f"{rel} declares gate-candidate-discovery feature but no "
                    "AGENT-CANDIDATES block contains a `#   run ` stub",
                    rel,
                )
        else:
            self.skip(
                f"{rel} gate-candidate-discovery feature not declared; stub population not required",
                rel,
            )

    def validate_hook_templates(self) -> None:
        self.exists("core/hooks/session-start.sh")
        self.shell_syntax("core/hooks/session-start.sh")
        self.exists("core/hooks/pre-tool-use-secret-guard.py.template")
        self.py_compile(
            ["core/hooks/pre-tool-use-secret-guard.py.template"],
            "core/hooks/pre-tool-use-secret-guard.py.template compiles",
        )
        self.contains(
            "core/hooks/pre-tool-use-secret-guard.py.template",
            "hookSpecificOutput",
            "core/hooks/pre-tool-use-secret-guard.py.template emits hookSpecificOutput envelope",
        )
        self.contains(
            "core/hooks/pre-tool-use-secret-guard.py.template",
            "permissionDecision",
            "core/hooks/pre-tool-use-secret-guard.py.template emits permissionDecision",
        )
        readme = "core/hooks/README.md"
        self.exists(readme)
        self.contains(readme, "off by default", f"{readme} states hooks are off by default")
        self.contains(readme, "user credentials", f"{readme} warns hooks run with user credentials")
        self.contains(readme, "schema", f"{readme} requires schema verification before registration")
        self.contains(readme, "Manual registration", f"{readme} documents manual registration step")
        self.contains(readme, "secret-guard", f"{readme} documents secret-guard hook")
        self.contains(readme, "session-start", f"{readme} documents session-start hook")

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

    def validate_claude_native_subagents(self) -> None:
        expected_roles = ("planner", "implementer", "reviewer", "gate-runner")
        required_fields = ("name", "description", "tools", "permissionMode", "maxTurns", "skills")
        for role in expected_roles:
            rel = f".claude/agents/{role}.md"
            path = self.root / rel
            if not path.is_file():
                self.fail(f"{rel} is missing", rel)
                continue
            text = read_text(path)
            match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
            if not match:
                self.fail(f"{rel} missing valid frontmatter block", rel)
                continue
            frontmatter = match.group(1)
            for field in required_fields:
                if re.search(rf"^{field}:\s+\S", frontmatter, re.MULTILINE):
                    self.pass_(f"{rel} frontmatter contains {field}", rel)
                else:
                    self.fail(f"{rel} frontmatter missing {field}", rel)
            if re.search(r"^model:\s*\S", frontmatter, re.MULTILINE):
                self.fail(f"{rel} frontmatter must not pin model", rel)
            else:
                self.pass_(f"{rel} frontmatter does not pin model", rel)
            if re.search(rf"^name:\s+{re.escape(role)}\s*$", frontmatter, re.MULTILINE):
                self.pass_(f"{rel} frontmatter name equals {role}", rel)
            else:
                self.fail(f"{rel} frontmatter name must equal {role}", rel)

    def manifest_has_feature(self, data: dict[str, Any] | None, feature: str) -> bool:
        return isinstance(data, dict) and feature in (data.get("features_enabled") or [])

    def check_placeholders(self) -> None:
        matches: list[str] = []
        for item in generated_text_files(self.root):
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
                for item in generated_text_files(self.root):
                    if BOOTSTRAP_COMPLETION_MARKER in read_text(item):
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
        if (self.root / "scripts/lib/insert_gate_candidates.py").is_file():
            self.py_compile(
                ["scripts/lib/insert_gate_candidates.py"],
                "scripts/lib/insert_gate_candidates.py compiles",
            )

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

        for adapter in THIN_ADAPTER_GENERATED_PATHS:
            path = self.root / adapter
            if path.exists():
                if ".agent/" in read_text(path):
                    self.pass_(f"{adapter} points to .agent/", adapter)
                else:
                    self.fail(f"{adapter} exists but does not point to .agent/", adapter)
                for heading in THIN_ADAPTER_TIER_HEADINGS:
                    self.contains(adapter, heading, f"{adapter} includes {heading}")
            else:
                self.skip(f"{adapter} not generated", adapter)

        if self.manifest_has_feature(manifest, "claude-native-subagents"):
            self.validate_claude_native_subagents()
        elif (self.root / ".claude/agents").is_dir():
            self.skip(".claude/agents present without claude-native-subagents feature; skipping native subagent checks", ".claude/agents")
        else:
            self.skip(".claude/agents not expected without claude-native-subagents feature", ".claude/agents")

        self.validate_gate_candidate_markers_generated(manifest)

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
