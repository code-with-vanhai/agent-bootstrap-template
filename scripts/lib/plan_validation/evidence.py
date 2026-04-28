from __future__ import annotations

import re
from typing import List, Optional, Tuple

from .markdown import _FENCE_RE, _line_of_offset
from .models import EvidenceBlock


# ---------------------------------------------------------------------------


_EVIDENCE_OPEN_RE = re.compile(
    r"<!--\s*current-code\s+(?P<attrs>[^>]*?)\s*-->",
    re.MULTILINE,
)
_EVIDENCE_CLOSE_RE = re.compile(r"<!--\s*/current-code\s*-->", re.MULTILINE)
_ATTR_RE = re.compile(r"(?P<key>[a-z_][a-z0-9_]*)\s*=\s*(?P<value>\S+)")
_WS_COLLAPSE_RE = re.compile(r"\s+")


def normalize_whitespace(text: str) -> str:
    """Collapse all whitespace runs to single space and strip trailing whitespace.

    Implementation note: we strip per-line trailing whitespace then collapse
    interior runs. This makes `region_sha256` insensitive to indentation drift
    inside the snippet body but still detects character-level tampering.
    """

    lines = [ln.rstrip() for ln in text.splitlines()]
    joined = "\n".join(lines).strip()
    return _WS_COLLAPSE_RE.sub(" ", joined)


def parse_evidence_blocks(plan_text: str) -> List[EvidenceBlock]:
    blocks: List[EvidenceBlock] = []
    pos = 0
    while True:
        open_match = _EVIDENCE_OPEN_RE.search(plan_text, pos)
        if not open_match:
            break
        close_match = _EVIDENCE_CLOSE_RE.search(plan_text, open_match.end())
        if not close_match:
            # Unclosed block; record with what we have.
            attrs = _parse_attrs(open_match.group("attrs"))
            blocks.append(
                EvidenceBlock(
                    start_line=_line_of_offset(plan_text, open_match.start()),
                    end_line=_line_of_offset(plan_text, len(plan_text)),
                    raw_attrs=open_match.group("attrs"),
                    path=attrs.get("path"),
                    lines=_parse_lines(attrs.get("lines")),
                    ref=attrs.get("ref"),
                    region_sha256=attrs.get("region_sha256"),
                    snippet="",
                    snippet_offset=open_match.end(),
                )
            )
            break

        body_offset = open_match.end()
        body = plan_text[body_offset : close_match.start()]
        snippet = _extract_snippet_from_body(body)
        attrs = _parse_attrs(open_match.group("attrs"))
        blocks.append(
            EvidenceBlock(
                start_line=_line_of_offset(plan_text, open_match.start()),
                end_line=_line_of_offset(plan_text, close_match.end()),
                raw_attrs=open_match.group("attrs"),
                path=attrs.get("path"),
                lines=_parse_lines(attrs.get("lines")),
                ref=attrs.get("ref"),
                region_sha256=attrs.get("region_sha256"),
                snippet=snippet,
                snippet_offset=body_offset,
            )
        )
        pos = close_match.end()
    return blocks


def _parse_attrs(raw: str) -> dict:
    return {m.group("key"): m.group("value") for m in _ATTR_RE.finditer(raw)}


def _parse_lines(raw: Optional[str]) -> Optional[Tuple[int, int]]:
    if not raw:
        return None
    match = re.match(r"^(\d+)-(\d+)$", raw)
    if not match:
        return None
    a, b = int(match.group(1)), int(match.group(2))
    if a < 1 or b < a:
        return None
    return a, b


def _extract_snippet_from_body(body: str) -> str:
    """Extract the snippet from inside an evidence block body.

    The contract (see `core/workflows/feature-workflow.md`) says the validator
    parses by HTML comment boundary, not by markdown fence, so the snippet may
    contain triple-backticks. We achieve that here by stripping at most ONE
    outer fence wrapper if the body opens with a fence and ends with the same-
    width closing fence on its own line. Otherwise the body is returned as-is.
    """

    lines = body.splitlines()
    # Skip leading blank lines.
    start = 0
    while start < len(lines) and lines[start].strip() == "":
        start += 1
    # Skip trailing blank lines.
    end = len(lines)
    while end > start and lines[end - 1].strip() == "":
        end -= 1
    if start >= end:
        return ""

    open_match = _FENCE_RE.match(lines[start].strip())
    close_match = _FENCE_RE.match(lines[end - 1].strip()) if end - 1 > start else None
    if (
        open_match
        and close_match
        and open_match.group(1) == close_match.group(1)
        # Closer must be a bare fence (no info string), to avoid swallowing a
        # nested ```ts opener as the closer.
        and close_match.group(2).strip() == ""
    ):
        return "\n".join(lines[start + 1 : end - 1])

    # No clean wrapping fence; return the trimmed body verbatim.
    return "\n".join(lines[start:end])
