"""Hook templates + Claude native subagent frontmatter checks."""

from __future__ import annotations

import re

from .core import AgentSystemValidator
from .runtime import read_text


def validate_hook_templates(validator: AgentSystemValidator) -> None:
    validator.exists("core/hooks/session-start.sh")
    validator.shell_syntax("core/hooks/session-start.sh")
    validator.exists("core/hooks/pre-tool-use-secret-guard.py.template")
    validator.py_compile(
        ["core/hooks/pre-tool-use-secret-guard.py.template"],
        "core/hooks/pre-tool-use-secret-guard.py.template compiles",
    )
    validator.contains(
        "core/hooks/pre-tool-use-secret-guard.py.template",
        "hookSpecificOutput",
        "core/hooks/pre-tool-use-secret-guard.py.template emits hookSpecificOutput envelope",
    )
    validator.contains(
        "core/hooks/pre-tool-use-secret-guard.py.template",
        "permissionDecision",
        "core/hooks/pre-tool-use-secret-guard.py.template emits permissionDecision",
    )
    validator.exists("core/hooks/pre-tool-use-rulebase-guard.py.template")
    validator.py_compile(
        ["core/hooks/pre-tool-use-rulebase-guard.py.template"],
        "core/hooks/pre-tool-use-rulebase-guard.py.template compiles",
    )
    validator.contains(
        "core/hooks/pre-tool-use-rulebase-guard.py.template",
        "hookSpecificOutput",
        "core/hooks/pre-tool-use-rulebase-guard.py.template emits hookSpecificOutput envelope",
    )
    validator.contains(
        "core/hooks/pre-tool-use-rulebase-guard.py.template",
        ".agent/constitution.md",
        "core/hooks/pre-tool-use-rulebase-guard.py.template guards constitution path",
    )
    validator.contains(
        "core/hooks/pre-tool-use-rulebase-guard.py.template",
        ".agent/rulebase.md",
        "core/hooks/pre-tool-use-rulebase-guard.py.template guards rulebase path",
    )
    readme = "core/hooks/README.md"
    validator.exists(readme)
    validator.contains(readme, "off by default", f"{readme} states hooks are off by default")
    validator.contains(
        readme, "user credentials", f"{readme} warns hooks run with user credentials"
    )
    validator.contains(
        readme, "schema", f"{readme} requires schema verification before registration"
    )
    validator.contains(
        readme, "Manual registration", f"{readme} documents manual registration step"
    )
    validator.contains(readme, "secret-guard", f"{readme} documents secret-guard hook")
    validator.contains(readme, "session-start", f"{readme} documents session-start hook")
    validator.contains(readme, "rulebase-guard", f"{readme} documents rulebase-guard hook")


def validate_claude_native_subagents(validator: AgentSystemValidator) -> None:
    expected_roles = ("planner", "implementer", "reviewer", "gate-runner")
    required_fields = (
        "name",
        "description",
        "tools",
        "permissionMode",
        "maxTurns",
        "skills",
    )
    for role in expected_roles:
        rel = f".claude/agents/{role}.md"
        path = validator.root / rel
        if not path.is_file():
            validator.fail(f"{rel} is missing", rel)
            continue
        text = read_text(path)
        match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
        if not match:
            validator.fail(f"{rel} missing valid frontmatter block", rel)
            continue
        frontmatter = match.group(1)
        for field in required_fields:
            if re.search(rf"^{field}:\s+\S", frontmatter, re.MULTILINE):
                validator.pass_(f"{rel} frontmatter contains {field}", rel)
            else:
                validator.fail(f"{rel} frontmatter missing {field}", rel)
        if re.search(r"^model:\s*\S", frontmatter, re.MULTILINE):
            validator.fail(f"{rel} frontmatter must not pin model", rel)
        else:
            validator.pass_(f"{rel} frontmatter does not pin model", rel)
        if re.search(rf"^name:\s+{re.escape(role)}\s*$", frontmatter, re.MULTILINE):
            validator.pass_(f"{rel} frontmatter name equals {role}", rel)
        else:
            validator.fail(f"{rel} frontmatter name must equal {role}", rel)
