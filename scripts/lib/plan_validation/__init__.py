"""Modular implementation for `scripts.lib.validate_plan`."""

from .cli import main
from .evidence import normalize_whitespace, parse_evidence_blocks
from .markdown import (
    find_ac_table,
    find_table_under_section,
    section_body_lines,
    section_present,
)
from .models import (
    EvidenceBlock,
    Finding,
    MarkdownTable,
    PlanFile,
    RepoContext,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
)
from .repo_context import detect_repo_context
from .tables import artifact_status
from .validator import (
    collect_plan_files,
    detect_target_template_version,
    filter_for_exit,
    slice_lines,
    validate_plan,
)

__all__ = [
    "EvidenceBlock",
    "Finding",
    "MarkdownTable",
    "PlanFile",
    "RepoContext",
    "SEVERITY_HIGH",
    "SEVERITY_MEDIUM",
    "artifact_status",
    "collect_plan_files",
    "detect_repo_context",
    "detect_target_template_version",
    "filter_for_exit",
    "find_ac_table",
    "find_table_under_section",
    "main",
    "normalize_whitespace",
    "parse_evidence_blocks",
    "section_body_lines",
    "section_present",
    "slice_lines",
    "validate_plan",
]
