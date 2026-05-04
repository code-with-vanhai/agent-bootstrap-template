"""Generated-mode validation orchestrator + constitution/manifest checks.

Generated mode runs against a downstream repo that has had
``scripts/bootstrap-request.sh`` applied. It is more permissive than
template mode (legacy 0.9.0 layouts must keep working) but still
catches missing canonical files, broken adapter pointers, and
constitution/rulebase drift.
"""

from __future__ import annotations

from typing import Any

from .checks_adapters import validate_generated_adapters
from .checks_gates import (
    validate_gate_candidate_markers_generated,
    validate_gate_modes_manifest_generated,
)
from .checks_hooks import validate_claude_native_subagents
from .checks_template import (
    validate_command_files,
    validate_github_metadata,
    validate_worktree,
)
from .constants import (
    AUDIT_LOG_TRAP_MARKER,
    BOOTSTRAP_COMPLETION_MARKER,
    PLACEHOLDER_RE,
)
from .core import AgentSystemValidator
from .runtime import generated_text_files, read_text, version_at_least


def validate_manifest_shape(
    validator: AgentSystemValidator, rel: str
) -> dict[str, Any] | None:
    data = validator.json_file(rel, f"{rel} is valid JSON")
    if data is None:
        return None
    required = (
        "template_version",
        "canonical_root",
        "features_enabled",
        "project",
        "canonical_files",
        "verification",
        "tool_adapters",
        "notes",
    )
    for key in required:
        if key in data:
            validator.pass_(f"{rel} includes required field {key}", rel)
        else:
            validator.fail(f"{rel} missing required field {key}", rel)
    if data.get("canonical_root") != ".agent":
        validator.fail(f"{rel} canonical_root must be .agent", rel)
    verification = data.get("verification")
    if isinstance(verification, dict):
        if verification.get("entrypoint") == "scripts/agent-eval.sh":
            validator.pass_(f"{rel} verification entrypoint is scripts/agent-eval.sh", rel)
        else:
            validator.fail(f"{rel} verification entrypoint must be scripts/agent-eval.sh", rel)
        modes = verification.get("gate_modes")
        if isinstance(modes, list) and all(mode in modes for mode in validator._gate_modes):
            validator.pass_(f"{rel} includes all expected gate modes", rel)
        else:
            validator.fail(f"{rel} missing expected gate modes", rel)
    else:
        validator.fail(f"{rel} verification must be an object", rel)
    if not isinstance(data.get("features_enabled"), list):
        validator.fail(f"{rel} features_enabled must be an array", rel)
    project = data.get("project")
    if not isinstance(project, dict):
        validator.fail(f"{rel} project must be an object", rel)
    adapters = data.get("tool_adapters")
    if not isinstance(adapters, dict) or not all(
        isinstance(value, str) for value in adapters.values()
    ):
        validator.fail(f"{rel} tool_adapters must map tool names to paths", rel)
    return data


def validate_constitution_generated(
    validator: AgentSystemValidator, manifest: dict[str, Any] | None
) -> None:
    """Validate ``.agent/constitution.md`` with legacy-aware gating.

    Five outcomes:
      A. constitution exists -> validate required phrases + rulebase pointer.
      B. missing + manifest ``instantiated_from_template_version`` >= 0.10.0
         -> FAIL (migration required).
      C. missing + rulebase still references ``.agent/constitution.md``
         -> FAIL (broken bootstrap; trimmed rulebase + deleted constitution).
      D. missing + rulebase carries legacy ``NO COMPLETION CLAIMS`` phrase
         and no pointer -> SKIP (genuine pre-0.10.0 layout).
      E. missing + neither pointer nor legacy phrase -> FAIL (rulebase
         diverged too far from both layouts; refuse to silently pass).
    """

    rel_const = ".agent/constitution.md"
    constitution_path = validator.root / rel_const

    manifest_ver: str | None = None
    if isinstance(manifest, dict):
        raw_ver = manifest.get("instantiated_from_template_version")
        if isinstance(raw_ver, str):
            manifest_ver = raw_ver

    rulebase_rel = ".agent/rulebase.md"

    if constitution_path.is_file():
        validator.pass_(f"{rel_const} exists", rel_const)
        validator.contains(
            rel_const,
            "NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE",
            f"{rel_const} includes discipline gates",
        )
        validator.contains(
            rel_const,
            "Forbidden Without Explicit Human Approval",
            f"{rel_const} includes forbidden section heading",
        )
        validator.contains(
            rel_const,
            "Database & Migration Invariants",
            f"{rel_const} includes database invariants",
        )
        validator.contains(
            rulebase_rel,
            ".agent/constitution.md",
            ".agent/rulebase.md points to constitution",
        )
        return

    if version_at_least(manifest_ver, "0.10.0"):
        validator.fail(
            f"{rel_const} is required for manifests at template version 0.10.0 or newer",
            rel_const,
        )
        return

    rb_path = validator.root / rulebase_rel
    if not rb_path.is_file():
        validator.fail(f"{rulebase_rel} is missing", rulebase_rel)
        return
    rulebase_text = read_text(rb_path)
    if ".agent/constitution.md" in rulebase_text:
        validator.fail(
            f"{rel_const} is missing but {rulebase_rel} references it",
            rel_const,
        )
        return
    if "NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE" in rulebase_text:
        validator.skip(
            f"{rel_const} not present; legacy inline rulebase "
            f"(instantiated_from_template_version={manifest_ver!r})",
            rel_const,
        )
        return

    validator.fail(
        f"{rel_const} is missing and {rulebase_rel} is not a legacy inline rulebase",
        rel_const,
    )


def check_placeholders(validator: AgentSystemValidator) -> None:
    matches: list[str] = []
    for item in generated_text_files(validator.root):
        text = read_text(item)
        if PLACEHOLDER_RE.search(text):
            matches.append(item.relative_to(validator.root).as_posix())
    if matches:
        validator.fail(
            "placeholders remain in generated agent files: " + ", ".join(matches[:5])
        )
    else:
        validator.pass_("no template placeholders found")


def validate_generated(validator: AgentSystemValidator) -> None:
    validate_gate_modes_manifest_generated(validator)
    if (validator.root / ".agent").is_dir():
        check_placeholders(validator)
        if not (validator.root / ".agent/bootstrap-pending.md").is_file():
            marker_matches = []
            for item in generated_text_files(validator.root):
                if BOOTSTRAP_COMPLETION_MARKER in read_text(item):
                    marker_matches.append(
                        item.relative_to(validator.root).as_posix()
                    )
            if marker_matches:
                validator.fail(
                    "bootstrap completion markers remain after .agent/bootstrap-pending.md was removed"
                )
            else:
                validator.pass_("no bootstrap completion markers remain")
        else:
            validator.skip(
                "bootstrap completion marker check while .agent/bootstrap-pending.md exists"
            )
    else:
        validator.fail(".agent directory is missing", ".agent")

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
        "scripts/agent-audit-log.sh",
        "scripts/agent-eval.sh",
        "scripts/agent-gate-discover.sh",
        "scripts/agent-validate-plan.sh",
        "scripts/lib/audit_log.py",
        "scripts/lib/gate_discovery.py",
        "scripts/lib/validate_agent_system.py",
        "scripts/lib/validate_plan.py",
        "scripts/lib/plan_validation/cli.py",
        "scripts/lib/plan_validation/validator.py",
        "scripts/lib/agent_system_validation/__init__.py",
        "scripts/lib/agent_system_validation/cli.py",
    ):
        validator.exists(rel)

    manifest = validate_manifest_shape(validator, ".agent/manifest.json")
    validate_constitution_generated(validator, manifest)
    validator.contains(
        ".agent/rulebase.md",
        "Rationalization Checks",
        ".agent/rulebase.md includes rationalization checks",
    )
    validator.contains(
        ".agent/gates.md",
        "NO INVENTED GATES OR COMMANDS",
        ".agent/gates.md includes no-invented-gates discipline",
    )
    validator.contains(
        ".agent/project-profile.md",
        "## Data Surface",
        ".agent/project-profile.md includes Data Surface section",
    )

    validator.shell_syntax("scripts/agent-eval.sh")
    validator.shell_syntax("scripts/agent-audit-log.sh")
    validator.shell_syntax("scripts/agent-validate-plan.sh")
    validator.shell_syntax("scripts/agent-gate-discover.sh")
    plan_validation_files = [
        str(path.relative_to(validator.root))
        for path in (validator.root / "scripts/lib/plan_validation").glob("*.py")
    ]
    agent_system_validation_files = [
        str(path.relative_to(validator.root))
        for path in (
            validator.root / "scripts/lib/agent_system_validation"
        ).glob("*.py")
    ]
    validator.py_compile(
        ["scripts/lib/audit_log.py"], "scripts/lib/audit_log.py compiles"
    )
    validator.py_compile(
        ["scripts/lib/gate_discovery.py"], "scripts/lib/gate_discovery.py compiles"
    )
    validator.py_compile(
        ["scripts/lib/validate_agent_system.py"],
        "scripts/lib/validate_agent_system.py compiles",
    )
    validator.py_compile(
        agent_system_validation_files,
        "scripts/lib/agent_system_validation package compiles",
    )
    validator.py_compile(
        ["scripts/lib/validate_plan.py", *plan_validation_files],
        "scripts/lib/validate_plan.py and plan_validation package compile",
    )
    validator.contains(
        "scripts/agent-eval.sh",
        AUDIT_LOG_TRAP_MARKER,
        "scripts/agent-eval.sh installs audit-log EXIT trap",
    )
    validator.contains(
        "scripts/agent-validate-plan.sh",
        "agent-audit-log.sh",
        "scripts/agent-validate-plan.sh invokes audit-log wrapper",
    )
    if (validator.root / "scripts/lib/insert_gate_candidates.py").is_file():
        validator.py_compile(
            ["scripts/lib/insert_gate_candidates.py"],
            "scripts/lib/insert_gate_candidates.py compiles",
        )

    commands_enabled = (
        validator.root / ".agent/commands"
    ).is_dir() or validator.manifest_has_feature(manifest, "commands")
    if commands_enabled:
        validator.exists(".agent/workflows/release-check-workflow.md")
        validator.contains(
            ".agent/gates.md",
            "scripts/agent-eval.sh <mode>",
            ".agent/gates.md documents gate mode signature",
        )
        validate_command_files(validator, ".agent/commands")
    else:
        validator.skip(".agent/commands not generated for this repo")
        if (validator.root / ".agent/workflows/release-check-workflow.md").is_file():
            validator.contains(
                ".agent/workflows/release-check-workflow.md",
                "report-only",
                ".agent/workflows/release-check-workflow.md is report-only",
            )
        else:
            validator.skip(
                ".agent/workflows/release-check-workflow.md not generated for this repo"
            )

    validate_generated_adapters(validator)

    if validator.manifest_has_feature(manifest, "claude-native-subagents"):
        validate_claude_native_subagents(validator)
        validator.contains(
            ".claude/agents/implementer.md",
            r"^skills:.*\bdata-safety\b",
            ".claude/agents/implementer.md preloads data-safety skill",
            regex=True,
        )
    elif (validator.root / ".claude/agents").is_dir():
        validator.skip(
            ".claude/agents present without claude-native-subagents feature; skipping native subagent checks",
            ".claude/agents",
        )
    else:
        validator.skip(
            ".claude/agents not expected without claude-native-subagents feature",
            ".claude/agents",
        )

    validate_gate_candidate_markers_generated(validator, manifest)

    if (validator.root / ".github/PULL_REQUEST_TEMPLATE.md").is_file():
        validate_github_metadata(validator, ".github/PULL_REQUEST_TEMPLATE.md")
    else:
        validator.skip(
            ".github/PULL_REQUEST_TEMPLATE.md not generated",
            ".github/PULL_REQUEST_TEMPLATE.md",
        )

    if (validator.root / ".agent/workflows/worktree-workflow.md").is_file():
        validate_worktree(validator, ".agent/workflows/worktree-workflow.md")
    else:
        validator.skip(
            ".agent/workflows/worktree-workflow.md not generated",
            ".agent/workflows/worktree-workflow.md",
        )
