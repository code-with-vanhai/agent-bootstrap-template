"""Template-mode validation orchestrator + constitution template checks.

Template mode runs against the agent-bootstrap-template repo itself
(``core/``, ``adapters/``, ``scripts/lib/`` source). It is the strictest
mode — every drift between gate manifest, command list, schema, hook
templates, etc. must fail loudly so a release cannot ship inconsistent
guidance.
"""

from __future__ import annotations

from .checks_adapters import validate_thin_adapter_file_template
from .checks_audit_log import validate_audit_log_templates
from .checks_gates import (
    validate_gate_candidate_markers_template,
    validate_gate_modes,
    validate_gate_modes_manifest_template,
)
from .checks_hooks import validate_hook_templates
from .checks_skills import (
    load_skill_manifest,
    validate_skill_count_docs,
    validate_skill_mapping,
    validate_skill_set,
)
from .constants import EXPECTED_COMMANDS, THIN_ADAPTER_SOURCE_FILES
from .core import AgentSystemValidator


def validate_command_files(
    validator: AgentSystemValidator, command_root: str
) -> None:
    for command in EXPECTED_COMMANDS:
        validator.exists(f"{command_root}/{command}.md")
    validator.contains(
        f"{command_root}/bootstrap.md",
        "agent-bootstrap --features standard --target .",
        f"{command_root}/bootstrap.md invokes plugin wrapper",
    )
    validator.contains(
        f"{command_root}/plan.md",
        "planning only",
        f"{command_root}/plan.md is phase-1 only",
    )
    validator.contains(
        f"{command_root}/bugfix.md",
        "bugfix-workflow.md",
        f"{command_root}/bugfix.md points to bugfix workflow",
    )
    validator.contains(
        f"{command_root}/implement.md",
        "implementation phase only",
        f"{command_root}/implement.md is implementation-phase only",
    )
    validator.contains(
        f"{command_root}/refactor.md",
        "refactor-workflow.md",
        f"{command_root}/refactor.md points to refactor workflow",
    )
    validator.contains(
        f"{command_root}/review.md",
        "review-workflow.md",
        f"{command_root}/review.md points to review workflow",
    )
    validator.contains(
        f"{command_root}/security-review.md",
        "security-review-workflow.md",
        f"{command_root}/security-review.md points to security review workflow",
    )
    validator.contains(
        f"{command_root}/verify.md",
        "scripts/agent-eval.sh <mode>",
        f"{command_root}/verify.md maps arguments to gate modes",
    )
    validator.contains(
        f"{command_root}/release-check.md",
        "release-check-workflow.md",
        f"{command_root}/release-check.md points to release-check workflow",
    )


def validate_mcp_template(validator: AgentSystemValidator) -> None:
    """Validate the opt-in MCP layer source files (Stage 5).

    Template-only checks. Generated repos do not need any MCP files unless
    the user opted in with ``--with-mcp-discovery`` at bootstrap time;
    runtime validation of an opt-in repo lives in
    ``scripts/lib/validate_mcp_config.py``.
    """

    validator.exists("core/mcp/README.md")
    rel = "core/mcp/catalog.json"
    data = validator.json_file(rel, f"{rel} is valid JSON")
    if data is not None:
        if data.get("schema_version") == 1:
            validator.pass_(f"{rel} schema_version is 1", rel)
        else:
            validator.fail(f"{rel} schema_version must be 1", rel)
        servers = data.get("servers")
        if isinstance(servers, dict) and servers:
            validator.pass_(f"{rel} declares {len(servers)} candidate server(s)", rel)
            for name, entry in servers.items():
                if not isinstance(entry, dict):
                    validator.fail(
                        f"{rel} servers.{name} must be an object", rel
                    )
                    continue
                for required in ("purpose", "applies_when", "auth_env"):
                    if required not in entry:
                        validator.fail(
                            f"{rel} servers.{name} missing required field {required}",
                            rel,
                        )
        else:
            validator.fail(f"{rel} servers must be a non-empty object", rel)
    validator.exists("core/mcp/.mcp.json.template")
    validator.contains(
        "core/mcp/.mcp.json.template",
        "${GITHUB_TOKEN}",
        "core/mcp/.mcp.json.template uses env var references for credentials",
    )
    validator.exists("core/commands/mcp-discover.md")
    validator.contains(
        "core/commands/mcp-discover.md",
        "report-only",
        "core/commands/mcp-discover.md is report-only",
    )
    validator.contains(
        "core/commands/mcp-discover.md",
        "Do not write `.mcp.json`",
        "core/commands/mcp-discover.md forbids writing .mcp.json",
    )
    validator.exists("scripts/lib/validate_mcp_config.py")
    validator.py_compile(
        ["scripts/lib/validate_mcp_config.py"],
        "scripts/lib/validate_mcp_config.py compiles",
    )


def validate_constitution_template(validator: AgentSystemValidator) -> None:
    validator.exists("core/constitution.template.md")
    validator.contains(
        "core/constitution.template.md",
        "NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE",
        "core/constitution.template.md includes discipline gates",
    )
    validator.contains(
        "core/constitution.template.md",
        "## Forbidden Without Explicit Human Approval",
        "core/constitution.template.md includes forbidden section",
    )
    validator.contains(
        "core/constitution.template.md",
        "## Database & Migration Invariants",
        "core/constitution.template.md includes database invariants",
    )
    validator.contains(
        "core/constitution.template.md",
        "## Amendment",
        "core/constitution.template.md includes amendment section",
    )
    validator.contains(
        "core/rulebase.template.md",
        ".agent/constitution.md",
        "core/rulebase.template.md points to constitution",
    )
    validator.contains(
        "core/workflows/rule-evolution-workflow.md",
        "## Out Of Scope",
        "core/workflows/rule-evolution-workflow.md excludes constitution edits",
    )
    validator.contains(
        "core/workflows/rule-evolution-workflow.md",
        ".agent/constitution.md",
        "core/workflows/rule-evolution-workflow.md references constitution path",
    )
    validator.contains(
        "core/manifest.template.json",
        '".agent/constitution.md"',
        "core/manifest.template.json lists constitution in canonical_files",
    )


def validate_github_metadata(validator: AgentSystemValidator, rel: str) -> None:
    validator.exists(rel)
    validator.contains(rel, "Problem observed", f"{rel} includes problem observed section")
    validator.contains(rel, "Gates run", f"{rel} includes gates run section")
    validator.contains(
        rel,
        "fabricated problem statements, speculative fixes, or bundled unrelated changes",
        f"{rel} includes anti-slop warning",
    )


def validate_worktree(validator: AgentSystemValidator, rel: str) -> None:
    validator.exists(rel)
    validator.contains(rel, "optional acceleration", f"{rel} states opt-in behavior")
    validator.contains(rel, "Directory Priority", f"{rel} includes directory priority")
    validator.contains(rel, "Baseline Gate", f"{rel} includes baseline gate")
    validator.contains(rel, "When NOT To Use", f"{rel} includes when-not-to-use section")


def validate_template(validator: AgentSystemValidator) -> None:
    validator.exists("core/bootstrap-steps.md")
    validator.contains(
        "core/bootstrap-steps.md",
        "Deterministic Skeleton",
        "core/bootstrap-steps.md includes deterministic skeleton phase",
    )
    validator.contains(
        "core/bootstrap-steps.md",
        "Agent Completion",
        "core/bootstrap-steps.md includes agent completion phase",
    )

    validator.exists("scripts/bootstrap-request.sh")
    validator.contains(
        "scripts/bootstrap-request.sh",
        "--features",
        "scripts/bootstrap-request.sh supports feature selection",
    )
    validator.contains(
        "scripts/bootstrap-request.sh",
        "--harness",
        "scripts/bootstrap-request.sh supports harness selection",
    )
    validator.contains(
        "scripts/lib/bootstrap/render_token_map.sh",
        "FEATURES_ENABLED_JSON_ARRAY",
        "bootstrap render_token_map passes features_enabled JSON into token map",
    )
    validator.contains(
        "scripts/bootstrap-request.sh",
        "BOOTSTRAP_LIB",
        "bootstrap orchestrator sources scripts/lib/bootstrap helpers",
    )
    validator.shell_syntax("scripts/bootstrap-request.sh")
    bootstrap_lib = validator.root / "scripts/lib/bootstrap"
    if bootstrap_lib.is_dir():
        for path in sorted(bootstrap_lib.glob("*.sh")):
            helper = str(path.relative_to(validator.root))
            validator.shell_syntax(helper)
    else:
        validator.fail(
            "scripts/lib/bootstrap directory missing (Stage 4c modular bootstrap)",
            "scripts/lib/bootstrap",
        )

    validator.exists("scripts/agent-validate.sh")
    validator.shell_syntax("scripts/agent-validate.sh")
    validator.contains(
        "scripts/agent-validate.sh",
        "validate_agent_system.py",
        "scripts/agent-validate.sh invokes structured validator",
    )
    validator.exists("scripts/lib/validate_agent_system.py")
    validator.py_compile(
        ["scripts/lib/validate_agent_system.py"],
        "scripts/lib/validate_agent_system.py compiles",
    )
    agent_system_validation_files = [
        str(path.relative_to(validator.root))
        for path in (validator.root / "scripts/lib/agent_system_validation").glob("*.py")
    ]
    validator.exists("scripts/lib/agent_system_validation/__init__.py")
    validator.exists("scripts/lib/agent_system_validation/cli.py")
    validator.py_compile(
        agent_system_validation_files,
        "scripts/lib/agent_system_validation package compiles",
    )
    validate_audit_log_templates(validator)
    validator.exists("scripts/agent-lock.sh")
    validator.shell_syntax("scripts/agent-lock.sh")
    validator.exists("scripts/lib/agent_lock.py")
    validator.py_compile(
        ["scripts/lib/agent_lock.py"],
        "scripts/lib/agent_lock.py compiles",
    )
    validator.exists("scripts/lib/secret_scan_redacted.py")
    validator.py_compile(
        ["scripts/lib/secret_scan_redacted.py"],
        "scripts/lib/secret_scan_redacted.py compiles",
    )
    validator.exists("scripts/lib/gate_modes.py")
    validator.py_compile(
        ["scripts/lib/gate_modes.py"],
        "scripts/lib/gate_modes.py compiles",
    )
    validator.exists("scripts/lib/gate_runner.py")
    validator.py_compile(
        ["scripts/lib/gate_runner.py"],
        "scripts/lib/gate_runner.py compiles",
    )

    validator.exists("scripts/agent-validate-plan.sh")
    validator.shell_syntax("scripts/agent-validate-plan.sh")
    validator.exists("scripts/agent-gate-discover.sh")
    validator.shell_syntax("scripts/agent-gate-discover.sh")
    plan_validation_files = [
        str(path.relative_to(validator.root))
        for path in (validator.root / "scripts/lib/plan_validation").glob("*.py")
    ]
    validator.exists("scripts/lib/validate_plan.py")
    validator.exists("scripts/lib/plan_validation/cli.py")
    validator.exists("scripts/lib/plan_validation/validator.py")
    validator.py_compile(
        ["scripts/lib/validate_plan.py", *plan_validation_files],
        "scripts/lib/validate_plan.py and plan_validation package compile",
    )
    validator.exists("scripts/agent-sync.sh")
    validator.shell_syntax("scripts/agent-sync.sh")
    validator.contains(
        "scripts/agent-sync.sh",
        "agent-sync.py",
        "scripts/agent-sync.sh invokes agent-sync.py shim",
    )
    validator.exists("scripts/agent-sync.py")
    validator.py_compile(
        ["scripts/agent-sync.py"],
        "scripts/agent-sync.py compiles",
    )
    agent_sync_files = [
        str(path.relative_to(validator.root))
        for path in (validator.root / "scripts/lib/agent_sync").glob("*.py")
    ]
    validator.exists("scripts/lib/agent_sync/__init__.py")
    validator.exists("scripts/lib/agent_sync/cli.py")
    validator.py_compile(
        agent_sync_files,
        "scripts/lib/agent_sync package compiles",
    )
    validator.exists("scripts/lib/render_template.py")
    validator.py_compile(
        ["scripts/lib/render_template.py"],
        "scripts/lib/render_template.py compiles",
    )
    validator.exists("scripts/lib/gate_discovery.py")
    validator.py_compile(
        ["scripts/lib/gate_discovery.py"],
        "scripts/lib/gate_discovery.py compiles",
    )
    validator.exists("scripts/lib/insert_gate_candidates.py")
    validator.py_compile(
        ["scripts/lib/insert_gate_candidates.py"],
        "scripts/lib/insert_gate_candidates.py compiles",
    )

    validator.exists("core/manifest.schema.json")
    validator.json_file("core/manifest.schema.json", "core/manifest.schema.json is valid JSON")
    validator.exists("core/manifest.template.json")
    validator.contains(
        "core/manifest.template.json",
        '"features_enabled"',
        "core/manifest.template.json includes features_enabled",
    )
    validator.contains(
        "core/manifest.template.json",
        '"tool_adapters"',
        "core/manifest.template.json includes tool_adapters",
    )
    validator.contains(
        "core/manifest.template.json",
        '"verification"',
        "core/manifest.template.json includes verification",
    )
    validator.exists("core/project-profile.template.md")
    validator.contains(
        "core/project-profile.template.md",
        "## Data Surface",
        "core/project-profile.template.md includes Data Surface section",
    )

    validate_constitution_template(validator)

    validator.exists(".claude-plugin/plugin.json")
    validator.json_file(
        ".claude-plugin/plugin.json", ".claude-plugin/plugin.json is valid JSON"
    )
    validator.contains(
        ".claude-plugin/plugin.json",
        '"name": "agent-bootstrap"',
        ".claude-plugin/plugin.json defines agent-bootstrap plugin",
    )
    validator.contains(
        ".claude-plugin/plugin.json",
        '"skills": "./core/skills/"',
        ".claude-plugin/plugin.json points to canonical skills",
    )
    validator.contains(
        ".claude-plugin/plugin.json",
        '"commands": "./core/commands/"',
        ".claude-plugin/plugin.json points to canonical commands",
    )

    validator.exists("scripts/agent-eval.template.sh")
    validator.contains(
        "scripts/agent-eval.template.sh",
        "security)",
        "scripts/agent-eval.template.sh supports security gate mode",
    )
    validate_gate_modes_manifest_template(validator)
    validate_gate_modes(validator)
    validate_gate_candidate_markers_template(validator)

    validator.exists(".claude-plugin/marketplace.json")
    validator.json_file(
        ".claude-plugin/marketplace.json", ".claude-plugin/marketplace.json is valid JSON"
    )
    validator.contains(
        ".claude-plugin/marketplace.json",
        '"source": "./"',
        ".claude-plugin/marketplace.json installs plugin from repo root",
    )

    if (validator.root / "commands").is_dir():
        validator.fail(
            "root commands/ directory should not exist; use canonical core/commands/",
            "commands",
        )
    else:
        validator.pass_("root commands/ directory is absent", "commands")

    validator.exists("core/command-conventions.md")
    validator.contains(
        "core/command-conventions.md",
        "Do not keep a second plugin-specific copy",
        "core/command-conventions.md includes drift rule",
    )
    validate_command_files(validator, "core/commands")

    validator.exists("bin/agent-bootstrap")
    validator.contains(
        "bin/agent-bootstrap",
        "--harness claude",
        "bin/agent-bootstrap defaults to Claude harness",
    )
    validator.shell_syntax("bin/agent-bootstrap")

    validate_github_metadata(validator, "core/github/PULL_REQUEST_TEMPLATE.md")
    validator.exists("core/github/agent-template-ci.example.yml")
    validator.contains(
        "core/github/agent-template-ci.example.yml",
        "scripts/agent-validate.sh",
        "core/github/agent-template-ci.example.yml runs agent validation",
    )
    validator.contains(
        "core/github/agent-template-ci.example.yml",
        "not configured",
        "core/github/agent-template-ci.example.yml handles not-configured fast gate",
    )

    validate_worktree(validator, "core/workflows/worktree-workflow.md")
    validator.exists("core/workflows/release-check-workflow.md")
    validator.contains(
        "core/workflows/release-check-workflow.md",
        "report-only",
        "core/workflows/release-check-workflow.md is report-only",
    )
    validator.contains(
        "core/workflows/release-check-workflow.md",
        "Do not deploy",
        "core/workflows/release-check-workflow.md forbids deploy",
    )

    validator.exists("core/skills/README.md")
    validator.contains(
        "core/skills/README.md",
        "Skill Mapping",
        "core/skills/README.md includes skill mapping",
    )
    validator.contains(
        "core/skills/manifest.json",
        '"data-safety"',
        "core/skills/manifest.json lists data-safety",
    )
    skills = load_skill_manifest(validator)
    if skills:
        validate_skill_set(validator, skills)
        validate_skill_mapping(validator, skills)
        validate_skill_count_docs(validator, skills)

    validate_hook_templates(validator)
    validate_mcp_template(validator)
    for rel in THIN_ADAPTER_SOURCE_FILES:
        validate_thin_adapter_file_template(validator, rel)
