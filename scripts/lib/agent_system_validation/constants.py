"""Shared constants for the agent-system validator.

Module-level constants that are read by multiple check groups. Kept in one
place so a literal change (e.g. a new expected command, a new tier heading)
ripples through every consumer in a single edit.
"""

from __future__ import annotations

import re

EXPECTED_COMMANDS = (
    "bootstrap",
    "plan",
    "bugfix",
    "implement",
    "refactor",
    "review",
    "security-review",
    "verify",
    "release-check",
)

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

GENERATED_TEXT_ROOTS = (
    ".agent",
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".cursor",
    ".github",
)
GENERATED_SCAN_EXCLUDED_DIRS = {"__pycache__"}
GENERATED_SCAN_EXCLUDED_SUFFIXES = {".pyc"}

# Excluding bytecode is the load-bearing defense here: Python const-folds
# adjacent string literals and stores the joined value in .pyc files.
BOOTSTRAP_COMPLETION_MARKER = "not confirmed - complete " + ".agent/bootstrap-pending.md"

SEMVER_CORE_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")

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

GATE_CANDIDATE_MARKER_OPEN_FMT = (
    "# >>> AGENT-CANDIDATES gate={gate} — review before promoting <<<"
)
GATE_CANDIDATE_MARKER_CLOSE_FMT = "# <<< END AGENT-CANDIDATES gate={gate} <<<"
GATE_CANDIDATE_RUN_RE = re.compile(r"^\s*#\s+run\s+\S", re.MULTILINE)
AUDIT_LOG_TRAP_MARKER = "trap '_audit_emit_gate_exit' EXIT"
