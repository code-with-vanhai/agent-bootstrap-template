from __future__ import annotations

import re
from typing import Iterable, List, Optional, Tuple

from .models import MarkdownTable




_FENCE_RE = re.compile(r"^(`{3,})(.*)$")


def _strip_fenced_blocks(text: str) -> str:
    """Return the text with fenced code blocks replaced by blank lines.

    Used to suppress self-claim regexes inside quoted code/discussion blocks so
    that referencing a banned phrase as documentation is not flagged.
    """

    out_lines: List[str] = []
    in_fence = False
    fence_marker = ""
    for line in text.splitlines():
        match = _FENCE_RE.match(line.strip())
        if match:
            marker = match.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = ""
            out_lines.append("")
            continue
        if in_fence:
            out_lines.append("")
        else:
            out_lines.append(line)
    return "\n".join(out_lines)


def _iter_fenced_code_blocks(text: str) -> Iterable[Tuple[int, str, str]]:
    """Yield (start_line, language, body) for each fenced code block.

    `start_line` is 1-indexed and points to the opening fence.
    Nested fences using a longer marker are tolerated.
    """

    lines = text.splitlines()
    i = 0
    while i < len(lines):
        match = _FENCE_RE.match(lines[i].strip())
        if not match:
            i += 1
            continue
        marker = match.group(1)
        info_string = match.group(2).strip()
        language = info_string.split()[0] if info_string else ""
        start_line = i + 1
        body_lines: List[str] = []
        i += 1
        while i < len(lines):
            close_match = _FENCE_RE.match(lines[i].strip())
            if close_match and close_match.group(1) == marker:
                break
            body_lines.append(lines[i])
            i += 1
        yield start_line, language, "\n".join(body_lines)
        i += 1


def _line_of_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


def section_present(plan_text: str, heading: str) -> bool:
    target = heading.strip().lower()
    for match in _HEADING_RE.finditer(plan_text):
        if match.group(2).strip().lower() == target:
            return True
    return False


def section_body_lines(plan_text: str, heading: str) -> List[Tuple[int, str]]:
    """Return (1-indexed line, content) pairs of the body under `heading`.

    The body ends at the next heading of equal or shallower depth or EOF.
    """

    target = heading.strip().lower()
    lines = plan_text.splitlines()
    out: List[Tuple[int, str]] = []
    in_section = False
    section_depth = 0
    for idx, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if match:
            depth = len(match.group(1))
            title = match.group(2).strip().lower()
            if title == target:
                in_section = True
                section_depth = depth
                continue
            if in_section and depth <= section_depth:
                break
        if in_section:
            out.append((idx + 1, line))
    return out


def find_table_under_section(plan_text: str, heading: str) -> Optional[MarkdownTable]:
    """Return the first markdown table under `heading`, if one exists."""

    table_start: Optional[int] = None
    rows: List[List[str]] = []
    row_lines: List[int] = []
    for line_no, line in section_body_lines(plan_text, heading):
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if table_start is None:
                table_start = line_no
            rows.append(cells)
            row_lines.append(line_no)
        elif table_start is not None:
            # Table ended.
            break
    if table_start is None:
        return None
    return MarkdownTable(start_line=table_start, rows=rows, row_lines=row_lines)


def find_ac_table(plan_text: str) -> Optional[Tuple[int, List[List[str]]]]:
    """Return (start_line, rows) for backward-compatible callers."""

    table = find_table_under_section(plan_text, "Acceptance Criteria")
    if table is None:
        return None
    return table.start_line, table.rows


def _is_separator_row(row: List[str]) -> bool:
    return all(set(c) <= set("-: ") for c in row)


def _table_data_rows(table: MarkdownTable) -> List[Tuple[int, List[str]]]:
    if not table.rows:
        return []
    first_data_row = 2 if len(table.rows) > 1 and _is_separator_row(table.rows[1]) else 1
    return list(zip(table.row_lines[first_data_row:], table.rows[first_data_row:]))


def _normalized_header(cell: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", cell.lower())


def _find_header(headers: List[str], *tokens: str) -> Optional[int]:
    for idx, header in enumerate(headers):
        normalized = _normalized_header(header)
        if all(token in normalized for token in tokens):
            return idx
    return None
