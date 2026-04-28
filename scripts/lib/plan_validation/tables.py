from __future__ import annotations

import re
from typing import List, Optional, Tuple

from .markdown import _find_header, _strip_fenced_blocks, _table_data_rows, section_body_lines
from .models import MarkdownTable


# `_LABEL_BOUNDARY` matches optional markdown emphasis (`**`, `*`, `__`, `_`)
# or backticks before/after the label-colon junction. This makes SC checks
# resilient to common bolded "Status: Ready" / "**Quality target:** 9/10"
# variants we observed in the wild (BrainMap dogfood).
_LABEL_BOUNDARY = r"(?:[`*_]+\s*)?"
_COLON = r"(?:\s*[`*_]+)?\s*:\s*(?:[`*_]+\s*)?"

SELF_CLAIM_PATTERNS = {
    "SC-001": re.compile(
        r"Quality\s+target" + _COLON + r"\d+(?:\.\d+)?\s*/\s*10",
        re.IGNORECASE,
    ),
    "SC-002": re.compile(
        r"(?:^|[^A-Za-z])" + _LABEL_BOUNDARY + r"Score" + _COLON + r"\d+(?:\.\d+)?\s*/\s*10",
        re.IGNORECASE,
    ),
    "SC-003": re.compile(
        r"^\s*" + _LABEL_BOUNDARY + r"Status"
        + _COLON
        + r"(?:Ready|Done|Complete|Production[- ]?ready)\b.*",
        re.IGNORECASE | re.MULTILINE,
    ),
    "SC-004": re.compile(
        r"\bReady\s+for\s+(?:implementation|review|merge|production)\b",
        re.IGNORECASE,
    ),
}

# SC-003 / SC-004 should only fire OUTSIDE a `Verified with evidence:` clause.
_VERIFIED_PATTERN = re.compile(r"Verified\s+with\s+evidence:", re.IGNORECASE)

LINT_CONTAINS_PATTERN = re.compile(r"querySelector\([^)]*:contains\(")
LINT_RDOM_TEST_UTILS_PATTERN = re.compile(
    r"""from\s+['"]react-dom/test-utils['"]"""
)
LINT_VI_STUBGLOBAL_CHROME_PATTERN = re.compile(
    r"""vi\.stubGlobal\(\s*['"]chrome['"]"""
)


# ---------------------------------------------------------------------------
# Section / AC checks
# ---------------------------------------------------------------------------


REQUIRED_SECTION_HEADINGS = (
    "Implementation Plan",
    "Acceptance Criteria",
    "Existing Behaviors Preserved",
    "Verification",
)

# Bullet entries that explicitly mark "no behaviors to preserve" are allowed
# without citation. Anything else is treated as a real entry that must cite.
_EMPTY_BEHAVIOR_MARKERS = (
    "none",
    "n/a",
    "not applicable",
    "(none)",
    "no existing behavior",
    "no behaviors to preserve",
)

# Tokens that count as "this bullet cites an evidence block" for BEH-002.
# We accept either a current-code reference, a `path:line` style citation, or
# a `lines=` attribute echo, since the grammar lives in the workflow.
_CITATION_TOKENS_RE = re.compile(
    r"(?:current-code\b|lines\s*=\s*\d+\s*-\s*\d+|`[^`]+:\d+(?:-\d+)?`|@[A-Za-z0-9_./\-]+:\d+(?:-\d+)?)"
)

AC_VERIFICATION_ENUM = {
    "AUTOMATED-UNIT",
    "AUTOMATED-INTEGRATION",
    "AUTOMATED-E2E",
    "BUILD-OUTPUT",
    "TYPECHECK",
    "MANUAL",
}

_CONTRACT_EXCLUDED_LITERALS = AC_VERIFICATION_ENUM | {
    "ADD",
    "BUG",
    "DEFERRED",
    "DRAFT",
    "INTENTIONALLY",
    "KEEP",
    "MANUAL",
    "PRESERVED",
    "PROPOSED",
    "REMOVED",
    "RESOLVED",
    "UPDATE",
}

_STATUS_RE = re.compile(
    r"^\s*(?:\*\*)?Status(?:\*\*)?\s*:\s*(?:\*\*)?\s*(.+?)\s*$",
    re.IGNORECASE,
)
_OPEN_QUESTION_RE = re.compile(r"^\s*[-*+]\s+Q\s*:\s*(.+)", re.IGNORECASE)
_OPEN_QUESTION_RESOLUTION_RE = re.compile(
    r"^\s*[-*+]\s+(RESOLVED|DEFERRED)\s*:\s*\S+",
    re.IGNORECASE,
)
_HEDGED_IMPL_BULLET_RE = re.compile(
    r"^\s*[-*+]\s+(?:"
    r"(?:maybe|might|could)\b|"
    r"consider\s+(?:"
    r"add(?:ing)?|use|using|map(?:ping)?|update|updating|change|changing|"
    r"switch|switching|route|routing|move|moving|split|splitting|create|"
    r"creating|introduce|introducing|replace|replacing|wire|wiring|include|"
    r"including|set|setting|extend|extending|implement|implementing"
    r")\b|"
    r".*\b(or\s+add|or\s+use)\b"
    r")",
    re.IGNORECASE,
)
_AC_LITERAL_REQUIRED_RE = re.compile(r"\b(stable\s+code|error\s+code|status|enum)\b", re.IGNORECASE)
_AC_DOCUMENTS_RE = re.compile(r"\b(documents?|documented|comments?)\b", re.IGNORECASE)
_BACKTICK_LITERAL_RE = re.compile(r"`([^`\n]+)`")
_IDENTIFIER_LITERAL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]*$")
_CONTRACT_TRIGGER_RE = re.compile(
    r"\b("
    r"stable\s+code|error[- ]?code|status\s+value|enum|"
    r"message\s+literal|i18n\s+key|localized\s+key|"
    r"contract\s+value|literal\s+mapping|new\s+literal"
    r")\b",
    re.IGNORECASE,
)
_TEST_CHANGE_RE = re.compile(
    r"\b(add|adds|adding|new|update|updates|updating|modify|modifies|"
    r"keep|keeps|preserve|preserves)\b.{0,50}\btests?\b|"
    r"\btests?\b.{0,50}\b(add|adds|adding|new|update|updates|updating|"
    r"modify|modifies|keep|keeps|preserve|preserves)\b",
    re.IGNORECASE,
)
_RISK_MITIGATION_RE = re.compile(r"\bMitigation\s*:", re.IGNORECASE)
_NUMERIC_DECISION_TRIGGER_RE = re.compile(
    r"\b("
    r"threshold|timeout|debounce|limit|budget|quota|memory|heap|"
    r"nodes?|length|size|count|ms|mb|kb|"
    r"MAX_[A-Z0-9_]+|[A-Z0-9_]+_(?:LIMIT|TIMEOUT|MS|DELAY|SIZE|LENGTH|COUNT)"
    r")\b",
    re.IGNORECASE,
)
_FALLBACK_DECISION_TRIGGER_RE = re.compile(
    r"\b(fallback|empty|null|degraded|degrade|no[- ]content|too[- ]large)\b",
    re.IGNORECASE,
)
_HARNESS_DECISION_TRIGGER_RE = re.compile(
    r"\b("
    r"mock|stub|fake\s*timers?|fake[- ]timer|vi\.useFakeTimers|"
    r"runAllTimersAsync|MutationObserver|defineContentScript|"
    r"content[- ]script\s+(?:test|harness)|test\s+harness"
    r")\b",
    re.IGNORECASE,
)
_DECISION_TRIGGER_RE = re.compile(
    r"\b("
    r"fallback|empty|null|degraded|degrade|no[- ]content|too[- ]large|"
    r"threshold|timeout|debounce|limit|budget|quota|memory|heap|"
    r"nodes?|length|size|count|ms|mb|kb|MAX_[A-Z0-9_]+|"
    r"[A-Z0-9_]+_(?:LIMIT|TIMEOUT|MS|DELAY|SIZE|LENGTH|COUNT)|"
    r"matcher|matching|classifier|classify|parser|parse|blocklist|allowlist|"
    r"mock|stub|fake\s*timers?|fake[- ]timer|vi\.useFakeTimers|"
    r"runAllTimersAsync|MutationObserver|defineContentScript|"
    r"content[- ]script\s+(?:test|harness)|test\s+harness"
    r")\b",
    re.IGNORECASE,
)
_PRESERVED_CVT_ROW_RE = re.compile(
    r"\b(unchanged|no\s+change|not\s+changed|preserved\s+literal|existing\s+invariant)\b",
    re.IGNORECASE,
)

LAYOUT_API_TOKENS = (
    "clientHeight",
    "getBoundingClientRect",
    "scrollTop",
    "IntersectionObserver",
    "getComputedStyle",
)




def artifact_status(plan_text: str) -> Optional[str]:
    for line in plan_text.splitlines():
        match = _STATUS_RE.match(line)
        if match:
            return match.group(1).strip()
    return None


def _status_is_beyond_draft(status: Optional[str]) -> bool:
    if not status:
        return False
    return status.lower().startswith("proposed") or bool(_VERIFIED_PATTERN.search(status))


def _missing_contract_value_headers(table: MarkdownTable) -> List[str]:
    headers = table.rows[0] if table.rows else []
    required = [
        ("Literal", ("literal",)),
        ("Producer", ("producer",)),
        ("Consumer", ("consumer",)),
        ("User-facing behavior", ("user", "behavior")),
        ("Test", ("test",)),
    ]
    return [
        label
        for label, tokens in required
        if _find_header(headers, *tokens) is None
    ]


def _missing_test_delta_headers(table: MarkdownTable) -> List[str]:
    headers = table.rows[0] if table.rows else []
    required = [
        ("Test", ("test",)),
        ("Action", ("action",)),
        ("Why", ("why",)),
    ]
    return [
        label
        for label, tokens in required
        if _find_header(headers, *tokens) is None
    ]


def _missing_decision_ledger_headers(table: MarkdownTable) -> List[str]:
    headers = table.rows[0] if table.rows else []
    required = [
        ("Decision", ("decision",)),
        ("Chosen Behavior", ("chosen", "behavior")),
        ("Rationale", ("rationale",)),
        ("Alternatives Rejected", ("alternatives", "rejected")),
        ("Caller/User Impact", ("caller", "impact")),
        ("Verification", ("verification",)),
    ]
    return [
        label
        for label, tokens in required
        if _find_header(headers, *tokens) is None
    ]


def _semantic_decision_text(plan_text: str) -> str:
    sections = (
        "Implementation Plan",
        "Acceptance Criteria",
        "Risks",
        "Test Delta",
    )
    body = "\n".join(
        line
        for section in sections
        for _line_no, line in section_body_lines(plan_text, section)
    )
    return _strip_fenced_blocks(body)


def _cell_nonempty(cell: str) -> bool:
    value = cell.strip().strip("`").strip()
    return value not in {"", "-", "—", "n/a", "N/A", "none", "None"}


def _decision_row_satisfies(
    table: MarkdownTable,
    trigger: re.Pattern[str],
    required_headers: Tuple[str, ...],
) -> bool:
    if not table.rows:
        return False
    header_indices = {
        header: _find_header(table.rows[0], *header.split("."))
        for header in required_headers
    }
    if any(idx is None for idx in header_indices.values()):
        return False
    for _line_no, row in _table_data_rows(table):
        row_text = " | ".join(row)
        if not trigger.search(row_text):
            continue
        if all(
            idx < len(row) and _cell_nonempty(row[idx])
            for idx in header_indices.values()
            if idx is not None
        ):
            return True
    return False


def _cvt_rows_look_preserved_only(table: MarkdownTable) -> bool:
    rows = _table_data_rows(table)
    if not rows:
        return False
    return all(
        _PRESERVED_CVT_ROW_RE.search(" | ".join(row))
        for _line_no, row in rows
    )


def _candidate_contract_literals(plan_text: str) -> List[str]:
    candidates: List[str] = []
    for raw in _BACKTICK_LITERAL_RE.findall(_strip_fenced_blocks(plan_text)):
        literal = raw.strip()
        if not literal or not _IDENTIFIER_LITERAL_RE.match(literal):
            continue
        upper_literal = literal.upper()
        if upper_literal in _CONTRACT_EXCLUDED_LITERALS:
            continue
        if "/" in literal or "\\" in literal:
            continue
        if re.search(r"\.(?:md|sh|py|ts|tsx|js|jsx|json|yaml|yml)$", literal):
            continue
        candidates.append(literal)
    return candidates


def _contract_value_table_required(plan_text: str) -> bool:
    stripped = _strip_fenced_blocks(plan_text)
    candidates = _candidate_contract_literals(stripped)
    if not candidates:
        return False
    return bool(_CONTRACT_TRIGGER_RE.search(stripped))


_BOUNDARY_GROUPS = (
    ("background", re.compile(r"\b(background|service[- ]worker|sw)\b", re.IGNORECASE)),
    ("ui", re.compile(r"\b(side[- ]?panel|frontend|ui|client|react)\b", re.IGNORECASE)),
    ("content", re.compile(r"\b(content[- ]script|webpage|page\s+context)\b", re.IGNORECASE)),
    ("server", re.compile(r"\b(server|backend|api)\b", re.IGNORECASE)),
    ("extension", re.compile(r"\b(extension|browser\s+extension|chrome)\b", re.IGNORECASE)),
    ("worker", re.compile(r"\b(web\s+worker|worker\s+thread|main\s+thread)\b", re.IGNORECASE)),
)


def _boundary_groups_in_affected_areas(plan_text: str) -> List[str]:
    body = "\n".join(line for _line_no, line in section_body_lines(plan_text, "Affected Areas"))
    return [name for name, pattern in _BOUNDARY_GROUPS if pattern.search(body)]


_COMPAT_SCENARIOS = (
    ("old producer + new consumer", ("old producer", "new consumer")),
    ("new producer + old consumer", ("new producer", "old consumer")),
    ("unknown value", ("unknown",)),
    ("empty value", ("empty",)),
    ("missing field", ("missing", "field")),
)


def _missing_compat_scenarios(table: MarkdownTable) -> List[str]:
    row_texts = [" ".join(row).lower() for _line_no, row in _table_data_rows(table)]
    missing: List[str] = []
    for label, tokens in _COMPAT_SCENARIOS:
        if not any(all(token in row_text for token in tokens) for row_text in row_texts):
            missing.append(label)
    return missing


def _test_delta_required(plan_text: str) -> bool:
    sections = (
        "Implementation Plan",
        "Acceptance Criteria",
        "Docs/Tests/Contracts To Update",
        "Docs/tests/contracts to update",
    )
    body = "\n".join(
        line
        for section in sections
        for _line_no, line in section_body_lines(plan_text, section)
    )
    return bool(_TEST_CHANGE_RE.search(body))


__all__ = [name for name in globals() if not name.startswith("__")]
