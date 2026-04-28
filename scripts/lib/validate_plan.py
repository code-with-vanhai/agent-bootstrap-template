#!/usr/bin/env python3
"""Validate `.agent/runs/<slug>/plan.md` (and `spec.md`) artifacts.

Checks:

  EV-001 Evidence block parses (path/lines/ref/region_sha256 all present).
  EV-002 path is repo-root-relative, no `..`, file exists.
  EV-003 Snippet content matches working tree at lines=A-B (whitespace-normalized).
  EV-004 ref commit exists; if cited region at HEAD differs from same region at ref, warn STALE.
  EV-005 region_sha256 matches the full whitespace-normalized snippet.

  SC-001 No `Quality target: N/10` outside quoted blocks.
  SC-002 No `Score: N/10` outside quoted blocks.
  SC-003 No banned `Status:` self-claim line outside `Verified with evidence:` block.
  SC-004 No bare `Ready for ...` outside `Verified with evidence:` block.

  LP-001 No `querySelector(...:contains(...)` in code blocks.
  LP-002 No `from 'react-dom/test-utils'` if repo has React >= 19.
  LP-003 No `vi.stubGlobal('chrome', ...)` if repo is MV3 extension. (Medium; fails under --strict.)

  SECT-001 Non-trivial plan must contain `Acceptance Criteria`,
           `Existing Behaviors Preserved`, `Implementation Plan`, and
           `Verification` sections.
  BEH-001 If `Existing Behaviors Preserved` has any non-empty bullet, the plan
          must contain at least one `<!-- current-code -->` evidence block.
          Empty markers (`- none`, `- N/A`, ...) are tolerated.
  BEH-002 (Medium) Each non-empty Existing Behaviors Preserved bullet should
          carry an inline evidence-block citation marker.
  OQ-001  Open Questions are optional, but any `- Q:` entry must be paired with
          `- RESOLVED:` or `- DEFERRED:`. Unresolved Draft questions are Medium;
          Proposed/Verified questions are High.
  IMPL-001 (Medium) Implementation Plan bullets must not leave behavior-affecting
           choices hedged with `consider`, `maybe`, `could`, `or add`, etc.
  AC-001  Every AC table row declares a Verification Method enum value.
  AC-002  Layout-dependent ACs cannot be `AUTOMATED-UNIT` (jsdom rule).
  AC-003  ACs about codes/statuses/enums must name literal target values.
  AC-004  ACs about documentation/comments cannot be verified by TYPECHECK alone.

The validator is repo-aware: React version + MV3 detection drive LP-002 and LP-003.

Exit codes:
  0  no High failures (Medium failures only emit warnings unless --strict)
  1  at least one High failure, OR any Medium failure under --strict
  2  usage error
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Severity + finding model
# ---------------------------------------------------------------------------

SEVERITY_HIGH = "High"
SEVERITY_MEDIUM = "Medium"


@dataclass
class Finding:
    check_id: str
    severity: str
    message: str
    file: Optional[Path] = None
    line: Optional[int] = None

    def format_for_human(self) -> str:
        location = ""
        if self.file is not None:
            location = f"{self.file}"
            if self.line is not None:
                location += f":{self.line}"
            location = f" [{location}]"
        return f"  [{self.severity}] {self.check_id}{location}: {self.message}"

    def format_for_github(self) -> str:
        # ::error file=path,line=N::CHECK-ID severity=High message
        kind = "error" if self.severity == SEVERITY_HIGH else "warning"
        attrs = []
        if self.file is not None:
            attrs.append(f"file={self.file}")
        if self.line is not None:
            attrs.append(f"line={self.line}")
        prefix = f"::{kind}"
        if attrs:
            prefix += " " + ",".join(attrs)
        return f"{prefix}::{self.check_id} severity={self.severity} {self.message}"


# ---------------------------------------------------------------------------
# Repo context
# ---------------------------------------------------------------------------


@dataclass
class RepoContext:
    repo_root: Path
    react_version: Optional[str] = None
    is_mv3_extension: bool = False
    detected_signals: List[str] = field(default_factory=list)


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


_SEMVER_NUMERIC = re.compile(r"(\d+)")


def _react_major_version(spec: str) -> Optional[int]:
    if not spec:
        return None
    match = _SEMVER_NUMERIC.search(spec)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def detect_repo_context(repo_root: Path) -> RepoContext:
    ctx = RepoContext(repo_root=repo_root)

    package_json = _read_json(repo_root / "package.json") or {}
    deps = {}
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        deps.update(package_json.get(section, {}) or {})

    react_spec = deps.get("react")
    if react_spec:
        ctx.react_version = react_spec

    # MV3 detection: any of the signals counts.
    if "@types/chrome" in deps:
        ctx.is_mv3_extension = True
        ctx.detected_signals.append("package.json: @types/chrome")

    if (repo_root / "wxt.config.ts").is_file() or (repo_root / "wxt.config.js").is_file():
        ctx.is_mv3_extension = True
        ctx.detected_signals.append("wxt.config present")

    for manifest_candidate in (
        repo_root / "manifest.json",
        repo_root / "public" / "manifest.json",
        repo_root / "src" / "manifest.json",
    ):
        manifest = _read_json(manifest_candidate)
        if manifest and manifest.get("manifest_version") == 3:
            ctx.is_mv3_extension = True
            ctx.detected_signals.append(f"{manifest_candidate.name}: manifest_version=3")
            break

    # Test setup mocking chrome.runtime.
    test_setup_globs = (
        repo_root / "__tests__" / "setup.ts",
        repo_root / "__tests__" / "setup.js",
        repo_root / "tests" / "setup.ts",
        repo_root / "test" / "setup.ts",
        repo_root / "vitest.setup.ts",
    )
    for setup in test_setup_globs:
        if setup.is_file():
            try:
                content = setup.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "chrome.runtime" in content or "chromeRuntime" in content:
                ctx.is_mv3_extension = True
                ctx.detected_signals.append(f"{setup.name}: mocks chrome.runtime")
                break

    return ctx


# ---------------------------------------------------------------------------
# Markdown helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Evidence block parsing (EV-001..EV-005)
# ---------------------------------------------------------------------------


_EVIDENCE_OPEN_RE = re.compile(
    r"<!--\s*current-code\s+(?P<attrs>[^>]*?)\s*-->",
    re.MULTILINE,
)
_EVIDENCE_CLOSE_RE = re.compile(r"<!--\s*/current-code\s*-->", re.MULTILINE)
_ATTR_RE = re.compile(r"(?P<key>[a-z_][a-z0-9_]*)\s*=\s*(?P<value>\S+)")


@dataclass
class EvidenceBlock:
    start_line: int
    end_line: int
    raw_attrs: str
    path: Optional[str]
    lines: Optional[Tuple[int, int]]
    ref: Optional[str]
    region_sha256: Optional[str]
    snippet: str
    snippet_offset: int  # offset within plan text


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


# ---------------------------------------------------------------------------
# Self-claim and lint pack
# ---------------------------------------------------------------------------


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

LAYOUT_API_TOKENS = (
    "clientHeight",
    "getBoundingClientRect",
    "scrollTop",
    "IntersectionObserver",
    "getComputedStyle",
)


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


def find_ac_table(plan_text: str) -> Optional[Tuple[int, List[List[str]]]]:
    """Return (start_line, rows) of the first markdown table under
    `Acceptance Criteria`. Each row is a list of cell strings.

    Returns None if the section or table is missing.
    """

    lines = plan_text.splitlines()
    in_section = False
    table_start: Optional[int] = None
    rows: List[List[str]] = []
    for idx, line in enumerate(lines):
        heading = _HEADING_RE.match(line)
        if heading:
            if heading.group(2).strip().lower() == "acceptance criteria":
                in_section = True
                continue
            if in_section and table_start is None:
                # Hit next heading without finding a table.
                break
            if in_section and table_start is not None:
                # Section ended; stop.
                break
        if not in_section:
            continue
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if table_start is None:
                table_start = idx + 1
            rows.append(cells)
        elif table_start is not None:
            # Table ended.
            break
    if table_start is None:
        return None
    return table_start, rows


# ---------------------------------------------------------------------------
# Git helpers (best-effort; absence does not fail the validator)
# ---------------------------------------------------------------------------


def _git(repo_root: Path, *args: str) -> Optional[bytes]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _ref_exists(repo_root: Path, ref: str) -> bool:
    out = _git(repo_root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    return out is not None and bool(out.strip())


def _show_at_ref(repo_root: Path, ref: str, path: str) -> Optional[str]:
    out = _git(repo_root, "show", f"{ref}:{path}")
    if out is None:
        return None
    return out.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Main validator
# ---------------------------------------------------------------------------


@dataclass
class PlanFile:
    path: Path
    text: str


def collect_plan_files(target: Path) -> List[PlanFile]:
    if target.is_file():
        return [PlanFile(target, target.read_text(encoding="utf-8"))]
    if not target.is_dir():
        raise SystemExit(f"target does not exist: {target}")

    files: List[PlanFile] = []
    for name in ("plan.md", "spec.md"):
        candidate = target / name
        if candidate.is_file():
            files.append(PlanFile(candidate, candidate.read_text(encoding="utf-8")))
    return files


def slice_lines(file_text: str, line_a: int, line_b: int) -> Optional[str]:
    lines = file_text.splitlines()
    if line_a < 1 or line_b > len(lines) or line_a > line_b:
        return None
    return "\n".join(lines[line_a - 1 : line_b])


def validate_plan(
    plan: PlanFile,
    repo_ctx: RepoContext,
    strict: bool,
) -> List[Finding]:
    findings: List[Finding] = []
    text = plan.text

    # ------------------------------------------------------------------
    # Evidence blocks
    # ------------------------------------------------------------------
    blocks = parse_evidence_blocks(text)
    for block in blocks:
        # EV-001 — required attrs
        missing = []
        if not block.path:
            missing.append("path")
        if block.lines is None:
            missing.append("lines")
        if not block.ref:
            missing.append("ref")
        if not block.region_sha256:
            missing.append("region_sha256")
        if missing:
            findings.append(
                Finding(
                    "EV-001",
                    SEVERITY_HIGH,
                    f"evidence block missing attrs: {', '.join(missing)}",
                    plan.path,
                    block.start_line,
                )
            )
            # Without minimum attrs, skip dependent checks.
            continue

        # EV-002 — path safety + existence
        cited = block.path or ""
        if cited.startswith("/") or ".." in Path(cited).parts:
            findings.append(
                Finding(
                    "EV-002",
                    SEVERITY_HIGH,
                    f"path must be repo-relative without `..`: {cited}",
                    plan.path,
                    block.start_line,
                )
            )
            continue
        cited_path = repo_ctx.repo_root / cited
        if not cited_path.is_file():
            findings.append(
                Finding(
                    "EV-002",
                    SEVERITY_HIGH,
                    f"cited file does not exist at working tree: {cited}",
                    plan.path,
                    block.start_line,
                )
            )
            continue

        # EV-003 — snippet matches working tree at lines=A-B
        line_a, line_b = block.lines
        try:
            file_text = cited_path.read_text(encoding="utf-8")
        except OSError as exc:
            findings.append(
                Finding(
                    "EV-002",
                    SEVERITY_HIGH,
                    f"cannot read cited file {cited}: {exc}",
                    plan.path,
                    block.start_line,
                )
            )
            continue

        actual_region = slice_lines(file_text, line_a, line_b)
        if actual_region is None:
            findings.append(
                Finding(
                    "EV-003",
                    SEVERITY_HIGH,
                    f"lines={line_a}-{line_b} out of range for {cited}",
                    plan.path,
                    block.start_line,
                )
            )
            continue

        actual_norm = normalize_whitespace(actual_region)
        snippet_norm = normalize_whitespace(block.snippet)
        if actual_norm != snippet_norm:
            findings.append(
                Finding(
                    "EV-003",
                    SEVERITY_HIGH,
                    (
                        f"snippet does not match working tree at "
                        f"{cited}:{line_a}-{line_b}"
                    ),
                    plan.path,
                    block.start_line,
                )
            )

        # EV-005 — region_sha256 must hash the full normalized snippet
        expected_sha = hashlib.sha256(snippet_norm.encode("utf-8")).hexdigest()
        if block.region_sha256.lower() != expected_sha.lower():
            findings.append(
                Finding(
                    "EV-005",
                    SEVERITY_HIGH,
                    (
                        "region_sha256 does not match SHA-256 of the "
                        "whitespace-normalized snippet"
                    ),
                    plan.path,
                    block.start_line,
                )
            )

        # EV-004 — ref-vs-worktree drift on cited region (Medium)
        if not _ref_exists(repo_ctx.repo_root, block.ref):
            findings.append(
                Finding(
                    "EV-004",
                    SEVERITY_MEDIUM,
                    f"ref {block.ref} not found in repo (skipping STALE check)",
                    plan.path,
                    block.start_line,
                )
            )
        else:
            ref_text = _show_at_ref(repo_ctx.repo_root, block.ref, cited)
            if ref_text is not None:
                ref_region = slice_lines(ref_text, line_a, line_b)
                if ref_region is not None and normalize_whitespace(ref_region) != actual_norm:
                    findings.append(
                        Finding(
                            "EV-004",
                            SEVERITY_MEDIUM,
                            (
                                f"STALE: cited region in {cited}:{line_a}-{line_b} "
                                f"changed between ref={block.ref} and working tree"
                            ),
                            plan.path,
                            block.start_line,
                        )
                    )

    # ------------------------------------------------------------------
    # Self-claim (SC-001..SC-004)
    # ------------------------------------------------------------------
    text_no_code = _strip_fenced_blocks(text)

    for check_id, pattern in SELF_CLAIM_PATTERNS.items():
        for match in pattern.finditer(text_no_code):
            line = _line_of_offset(text_no_code, match.start())
            if check_id in ("SC-003", "SC-004"):
                # Allow if the same line / paragraph contains a Verified-with-evidence
                # clause.
                surrounding = text_no_code[max(0, match.start() - 200) : match.end() + 200]
                if _VERIFIED_PATTERN.search(surrounding):
                    continue
            severity = SEVERITY_HIGH if check_id in ("SC-001", "SC-002", "SC-003") else SEVERITY_MEDIUM
            findings.append(
                Finding(
                    check_id,
                    severity,
                    f"banned self-claim phrase: {match.group(0).strip()}",
                    plan.path,
                    line,
                )
            )

    # ------------------------------------------------------------------
    # Lint pack inside code blocks (LP-001..LP-003)
    # ------------------------------------------------------------------
    react_major = _react_major_version(repo_ctx.react_version or "")

    for fence_line, _lang, body in _iter_fenced_code_blocks(text):
        for match in LINT_CONTAINS_PATTERN.finditer(body):
            findings.append(
                Finding(
                    "LP-001",
                    SEVERITY_HIGH,
                    "querySelector with jQuery `:contains()` is invalid CSS",
                    plan.path,
                    fence_line + body[: match.start()].count("\n"),
                )
            )

        if react_major is not None and react_major >= 19:
            for match in LINT_RDOM_TEST_UTILS_PATTERN.finditer(body):
                findings.append(
                    Finding(
                        "LP-002",
                        SEVERITY_HIGH,
                        "`react-dom/test-utils` is deprecated in React 19+; import act from 'react'",
                        plan.path,
                        fence_line + body[: match.start()].count("\n"),
                    )
                )

        if repo_ctx.is_mv3_extension:
            for match in LINT_VI_STUBGLOBAL_CHROME_PATTERN.finditer(body):
                findings.append(
                    Finding(
                        "LP-003",
                        SEVERITY_MEDIUM,
                        "vi.stubGlobal('chrome', ...) overrides the existing MV3 chrome mock; "
                        "use (chrome.runtime.sendMessage as any).mockImplementation instead",
                        plan.path,
                        fence_line + body[: match.start()].count("\n"),
                    )
                )

    # ------------------------------------------------------------------
    # Required sections (SECT-001)
    # ------------------------------------------------------------------
    missing_sections = [h for h in REQUIRED_SECTION_HEADINGS if not section_present(text, h)]
    if missing_sections:
        findings.append(
            Finding(
                "SECT-001",
                SEVERITY_HIGH,
                f"plan is missing required sections: {', '.join(missing_sections)}",
                plan.path,
                1,
            )
        )

    # ------------------------------------------------------------------
    # Open Questions decision lock (OQ-001)
    # ------------------------------------------------------------------
    open_question_body = section_body_lines(text, "Open Questions")
    if open_question_body:
        status = artifact_status(text)
        severity = SEVERITY_HIGH if _status_is_beyond_draft(status) else SEVERITY_MEDIUM
        q_entries: List[Tuple[int, int]] = []
        for idx, (line_no, line) in enumerate(open_question_body):
            if _OPEN_QUESTION_RE.match(line):
                q_entries.append((idx, line_no))
        for q_idx, (body_idx, q_line_no) in enumerate(q_entries):
            next_body_idx = (
                q_entries[q_idx + 1][0]
                if q_idx + 1 < len(q_entries)
                else len(open_question_body)
            )
            resolution_lines = [
                line for _line_no, line in open_question_body[body_idx + 1 : next_body_idx]
                if _OPEN_QUESTION_RESOLUTION_RE.match(line)
            ]
            if not resolution_lines:
                findings.append(
                    Finding(
                        "OQ-001",
                        severity,
                        (
                            "Open Questions entry must have a following "
                            "`- RESOLVED:` or `- DEFERRED:` bullet"
                        ),
                        plan.path,
                        q_line_no,
                    )
                )

    # ------------------------------------------------------------------
    # Implementation Plan decision-completeness smell checks (IMPL-001)
    # ------------------------------------------------------------------
    implementation_body = section_body_lines(text, "Implementation Plan")
    for line_no, line in implementation_body:
        stripped = line.lstrip()
        if not stripped.startswith(("-", "*", "+")):
            continue
        if _HEDGED_IMPL_BULLET_RE.match(line):
            findings.append(
                Finding(
                    "IMPL-001",
                    SEVERITY_MEDIUM,
                    (
                        "Implementation Plan bullet leaves a behavior-affecting "
                        "choice hedged; make the decision explicit or move it to "
                        "Open Questions as RESOLVED/DEFERRED"
                    ),
                    plan.path,
                    line_no,
                )
            )

    # ------------------------------------------------------------------
    # BEH-001 / BEH-002 - Existing Behaviors Preserved must cite evidence
    # ------------------------------------------------------------------
    behavior_body = section_body_lines(text, "Existing Behaviors Preserved")
    behavior_bullets: List[Tuple[int, str]] = []
    for line_no, line in behavior_body:
        stripped = line.lstrip()
        if not stripped.startswith(("-", "*", "+")):
            continue
        bullet = stripped[1:].strip()
        if not bullet:
            continue
        if bullet.lower().rstrip(".") in _EMPTY_BEHAVIOR_MARKERS:
            continue
        behavior_bullets.append((line_no, bullet))

    if behavior_bullets and not blocks:
        findings.append(
            Finding(
                "BEH-001",
                SEVERITY_HIGH,
                (
                    "Existing Behaviors Preserved lists "
                    f"{len(behavior_bullets)} entr"
                    f"{'y' if len(behavior_bullets) == 1 else 'ies'} "
                    "but the plan contains no `<!-- current-code -->` evidence "
                    "block. Each behavior must be cited."
                ),
                plan.path,
                behavior_bullets[0][0],
            )
        )
    else:
        for line_no, bullet in behavior_bullets:
            if not _CITATION_TOKENS_RE.search(bullet):
                findings.append(
                    Finding(
                        "BEH-002",
                        SEVERITY_MEDIUM,
                        (
                            "Existing Behaviors Preserved entry has no inline "
                            "evidence-block citation (current-code/lines=A-B/`path:line`)"
                        ),
                        plan.path,
                        line_no,
                    )
                )

    # ------------------------------------------------------------------
    # AC verification method classification (AC-001 + AC-002)
    # ------------------------------------------------------------------
    ac_table = find_ac_table(text)
    if ac_table is not None:
        table_start, rows = ac_table
        if len(rows) >= 2:
            header_cells = [c.strip().lower() for c in rows[0]]
            method_col = None
            criterion_col = None
            for idx, cell in enumerate(header_cells):
                if "verification" in cell and "method" in cell:
                    method_col = idx
                    break
            if method_col is None:
                # fall back: any header containing "method" or "verification"
                for idx, cell in enumerate(header_cells):
                    if cell in ("method", "verification"):
                        method_col = idx
                        break
            for idx, cell in enumerate(header_cells):
                if "criterion" in cell:
                    criterion_col = idx
                    break

            if method_col is None:
                findings.append(
                    Finding(
                        "AC-001",
                        SEVERITY_HIGH,
                        "Acceptance Criteria table has no Verification Method column",
                        plan.path,
                        table_start,
                    )
                )
            else:
                # rows[0] = header; rows[1] = separator (---|---|...) skip if so.
                first_data_row = 2 if len(rows) > 1 and all(set(c) <= set("-: ") for c in rows[1]) else 1
                for r_idx, row in enumerate(rows[first_data_row:], start=first_data_row):
                    if method_col >= len(row):
                        continue
                    method_cell = row[method_col].strip()
                    # Strip backticks/code formatting.
                    method_token = method_cell.strip("`").upper()
                    method_token = method_token.split()[0] if method_token else ""
                    line_no = table_start + r_idx
                    if method_token not in AC_VERIFICATION_ENUM:
                        findings.append(
                            Finding(
                                "AC-001",
                                SEVERITY_HIGH,
                                f"AC row uses unknown Verification Method: {method_cell!r}",
                                plan.path,
                                line_no,
                            )
                        )
                        continue
                    if method_token == "AUTOMATED-UNIT":
                        row_text = " | ".join(row).lower()
                        if any(token.lower() in row_text for token in LAYOUT_API_TOKENS):
                            findings.append(
                                Finding(
                                    "AC-002",
                                    SEVERITY_HIGH,
                                    (
                                        "AC depends on a layout API "
                                        "(clientHeight/getBoundingClientRect/scrollTop/...) "
                                        "and cannot be AUTOMATED-UNIT in jsdom"
                                    ),
                                    plan.path,
                                    line_no,
                                )
                            )
                    if criterion_col is not None and criterion_col < len(row):
                        criterion_cell = row[criterion_col].strip()
                        if _AC_LITERAL_REQUIRED_RE.search(criterion_cell) and "`" not in criterion_cell:
                            findings.append(
                                Finding(
                                    "AC-003",
                                    SEVERITY_MEDIUM,
                                    (
                                        "AC mentions a code/status/enum but does not name "
                                        "a literal target value in backticks"
                                    ),
                                    plan.path,
                                    line_no,
                                )
                            )
                        if method_token == "TYPECHECK" and _AC_DOCUMENTS_RE.search(criterion_cell):
                            findings.append(
                                Finding(
                                    "AC-004",
                                    SEVERITY_MEDIUM,
                                    (
                                        "AC asks for documentation/comment coverage but uses "
                                        "TYPECHECK only; split manual doc review or choose a "
                                        "non-documentation criterion"
                                    ),
                                    plan.path,
                                    line_no,
                                )
                            )

    return findings


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def filter_for_exit(findings: List[Finding], strict: bool) -> List[Finding]:
    if strict:
        return findings
    # Non-strict: only High counts toward exit code.
    return [f for f in findings if f.severity == SEVERITY_HIGH]


_MIN_TEMPLATE_VERSION = (0, 4, 0)


def _semver_tuple(version: str) -> Tuple[int, int, int]:
    """Parse `MAJOR.MINOR.PATCH(-pre)` into a comparable tuple.

    Pre-release suffixes are dropped for the comparison; we only need the
    numeric prefix to decide whether a repo has synced to >= 0.4.0.
    """

    core = version.split("-", 1)[0].split("+", 1)[0]
    parts = core.split(".")
    out = []
    for value in parts[:3]:
        try:
            out.append(int(value))
        except ValueError:
            out.append(0)
    while len(out) < 3:
        out.append(0)
    return tuple(out[:3])  # type: ignore[return-value]


def detect_target_template_version(repo_root: Path) -> Optional[str]:
    """Read `.agent/manifest.json` if present and return the synced version.

    Falls back through the same key order as `agent-sync.py`'s
    `detect_current_version`: `synced_to_template_version` then
    `instantiated_from_template_version`.
    """

    manifest_path = repo_root / ".agent" / "manifest.json"
    data = _read_json(manifest_path)
    if not data:
        return None
    for key in ("synced_to_template_version", "instantiated_from_template_version"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate .agent/runs/<slug>/plan.md and spec.md artifacts."
    )
    parser.add_argument("target", help="Plan file or .agent/runs/<slug>/ directory")
    parser.add_argument("--strict", action="store_true", help="Treat Medium findings as failures")
    parser.add_argument("--repo-root", help="Override repo root for context detection")
    parser.add_argument("--format", choices=("human", "github"), default="human")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Validate even if the target repo has not yet synced to template >= 0.4.0",
    )
    args = parser.parse_args(argv)

    target = Path(args.target).resolve()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else _detect_repo_root(target)

    if not args.force:
        synced_version = detect_target_template_version(repo_root)
        if synced_version is not None and _semver_tuple(synced_version) < _MIN_TEMPLATE_VERSION:
            min_str = ".".join(str(p) for p in _MIN_TEMPLATE_VERSION)
            print(
                f"SKIP: target repo template version {synced_version} < {min_str}; "
                f"skipping plan validation. Pass --force to override.",
                file=sys.stderr,
            )
            return 0

    plan_files = collect_plan_files(target)
    if not plan_files:
        print(f"No plan.md or spec.md found at {target}", file=sys.stderr)
        return 2

    repo_ctx = detect_repo_context(repo_root)

    all_findings: List[Finding] = []
    for plan in plan_files:
        all_findings.extend(validate_plan(plan, repo_ctx, args.strict))

    # Render output.
    high_count = sum(1 for f in all_findings if f.severity == SEVERITY_HIGH)
    medium_count = sum(1 for f in all_findings if f.severity == SEVERITY_MEDIUM)

    if args.format == "github":
        for f in all_findings:
            print(f.format_for_github())
    else:
        for plan in plan_files:
            plan_findings = [f for f in all_findings if f.file == plan.path]
            print(f"{plan.path}:")
            if not plan_findings:
                print("  (no findings)")
                continue
            for f in plan_findings:
                print(f.format_for_human())
        print()
        print(f"Summary: {high_count} High, {medium_count} Medium "
              f"(strict={args.strict}, repo_root={repo_root})")
        if repo_ctx.detected_signals:
            print(f"Repo signals: {'; '.join(repo_ctx.detected_signals)}")
        if repo_ctx.react_version:
            print(f"React version: {repo_ctx.react_version}")

    failing = filter_for_exit(all_findings, args.strict)
    return 1 if failing else 0


def _detect_repo_root(start: Path) -> Path:
    cur = start if start.is_dir() else start.parent
    cur = cur.resolve()
    while cur != cur.parent:
        if (cur / ".git").exists() or (cur / "package.json").exists() or (cur / ".agent").is_dir():
            return cur
        cur = cur.parent
    return start.parent.resolve()


if __name__ == "__main__":
    raise SystemExit(main())
