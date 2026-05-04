"""Modular implementation for `scripts.lib.validate_agent_system`.

The single-file `scripts/lib/validate_agent_system.py` is now a thin
shim that delegates to :func:`agent_system_validation.cli.main`. Each
check group lives in its own module; the public surface re-exported
here is the union of names that previously lived at module level on
``validate_agent_system``.
"""

from __future__ import annotations

from .checks_adapters import (
    validate_generated_adapters,
    validate_thin_adapter_file_template,
)
from .checks_audit_log import validate_audit_log_templates
from .checks_gates import (
    validate_gate_candidate_markers_generated,
    validate_gate_candidate_markers_template,
    validate_gate_modes,
    validate_gate_modes_manifest_generated,
    validate_gate_modes_manifest_template,
)
from .checks_generated import (
    check_placeholders,
    validate_constitution_generated,
    validate_generated,
    validate_manifest_shape,
)
from .checks_hooks import validate_claude_native_subagents, validate_hook_templates
from .checks_skills import (
    load_skill_manifest,
    validate_skill_count_docs,
    validate_skill_mapping,
    validate_skill_set,
)
from .checks_template import (
    validate_command_files,
    validate_constitution_template,
    validate_github_metadata,
    validate_template,
    validate_worktree,
)
from .cli import main
from .constants import (
    AUDIT_LOG_TRAP_MARKER,
    BOOTSTRAP_COMPLETION_MARKER,
    EXPECTED_COMMANDS,
    GATE_CANDIDATE_MARKER_CLOSE_FMT,
    GATE_CANDIDATE_MARKER_OPEN_FMT,
    GATE_CANDIDATE_RUN_RE,
    NUMERIC_SKILL_COUNT_RE,
    PLACEHOLDER_RE,
    SEMVER_CORE_RE,
    SKILL_COUNT_WORDS,
    THIN_ADAPTER_GENERATED_PATHS,
    THIN_ADAPTER_SOURCE_FILES,
    THIN_ADAPTER_TIER_HEADINGS,
    WORD_SKILL_COUNT_RE,
)
from .core import AgentSystemValidator, Check
from .output import render_github, render_human, render_json
from .runtime import (
    detect_mode,
    generated_text_files,
    parse_skill_mapping_names,
    read_text,
    resolve_root,
    skill_count_mentions,
)
from .token_budget import validate_token_budget

__all__ = [
    "AUDIT_LOG_TRAP_MARKER",
    "AgentSystemValidator",
    "BOOTSTRAP_COMPLETION_MARKER",
    "Check",
    "EXPECTED_COMMANDS",
    "GATE_CANDIDATE_MARKER_CLOSE_FMT",
    "GATE_CANDIDATE_MARKER_OPEN_FMT",
    "GATE_CANDIDATE_RUN_RE",
    "NUMERIC_SKILL_COUNT_RE",
    "PLACEHOLDER_RE",
    "SEMVER_CORE_RE",
    "SKILL_COUNT_WORDS",
    "THIN_ADAPTER_GENERATED_PATHS",
    "THIN_ADAPTER_SOURCE_FILES",
    "THIN_ADAPTER_TIER_HEADINGS",
    "WORD_SKILL_COUNT_RE",
    "check_placeholders",
    "detect_mode",
    "generated_text_files",
    "load_skill_manifest",
    "main",
    "parse_skill_mapping_names",
    "read_text",
    "render_github",
    "render_human",
    "render_json",
    "resolve_root",
    "skill_count_mentions",
    "validate_audit_log_templates",
    "validate_claude_native_subagents",
    "validate_command_files",
    "validate_constitution_generated",
    "validate_constitution_template",
    "validate_gate_candidate_markers_generated",
    "validate_gate_candidate_markers_template",
    "validate_gate_modes",
    "validate_gate_modes_manifest_generated",
    "validate_gate_modes_manifest_template",
    "validate_generated",
    "validate_generated_adapters",
    "validate_github_metadata",
    "validate_hook_templates",
    "validate_manifest_shape",
    "validate_skill_count_docs",
    "validate_skill_mapping",
    "validate_skill_set",
    "validate_template",
    "validate_thin_adapter_file_template",
    "validate_token_budget",
    "validate_worktree",
]
