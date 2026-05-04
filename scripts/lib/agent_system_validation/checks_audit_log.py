"""Audit-log entrypoint, helper, and EXIT-trap wiring checks (template mode)."""

from __future__ import annotations

from .constants import AUDIT_LOG_TRAP_MARKER
from .core import AgentSystemValidator
from .runtime import read_text


def validate_audit_log_templates(validator: AgentSystemValidator) -> None:
    validator.exists("scripts/agent-audit-log.sh")
    validator.shell_syntax("scripts/agent-audit-log.sh")
    validator.exists("scripts/lib/audit_log.py")
    validator.py_compile(
        ["scripts/lib/audit_log.py"], "scripts/lib/audit_log.py compiles"
    )
    validator.contains(
        "scripts/agent-eval.template.sh",
        AUDIT_LOG_TRAP_MARKER,
        "scripts/agent-eval.template.sh installs audit-log EXIT trap",
    )
    validator.contains(
        "scripts/agent-eval.template.sh",
        "scripts/agent-audit-log.sh",
        "scripts/agent-eval.template.sh invokes audit-log wrapper",
    )
    validator.contains(
        "scripts/agent-validate-plan.sh",
        "agent-audit-log.sh",
        "scripts/agent-validate-plan.sh invokes audit-log wrapper",
    )
    plan_wrapper = validator.root / "scripts/agent-validate-plan.sh"
    if plan_wrapper.is_file() and "2>&1" in read_text(plan_wrapper):
        validator.fail(
            "scripts/agent-validate-plan.sh must not merge stderr into stdout with 2>&1",
            "scripts/agent-validate-plan.sh",
        )
    elif plan_wrapper.is_file():
        validator.pass_(
            "scripts/agent-validate-plan.sh does not merge stderr into stdout",
            "scripts/agent-validate-plan.sh",
        )
