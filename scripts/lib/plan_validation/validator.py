from __future__ import annotations

import hashlib
from pathlib import Path
from typing import List, Optional, Tuple

from .evidence import normalize_whitespace, parse_evidence_blocks
from .git_utils import _ref_exists, _show_at_ref
from .markdown import (
    _find_header,
    _iter_fenced_code_blocks,
    _line_of_offset,
    _strip_fenced_blocks,
    _table_data_rows,
    find_table_under_section,
    section_body_lines,
    section_present,
)
from .models import Finding, PlanFile, RepoContext, SEVERITY_HIGH, SEVERITY_MEDIUM
from .repo_context import _react_major_version, _read_json
from .tables import *  # noqa: F403 - preserve original module-level helper names.


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

    # `spec.md` participates in evidence/self-claim/lint validation, but the
    # sections and decision-completeness tables below are plan.md contracts.
    if plan.path.name == "spec.md":
        return findings

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
    # AC verification method classification (AC-001..AC-004)
    # ------------------------------------------------------------------
    ac_table = find_table_under_section(text, "Acceptance Criteria")
    if ac_table is not None:
        if len(ac_table.rows) >= 2:
            header_cells = [c.strip().lower() for c in ac_table.rows[0]]
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
                        ac_table.start_line,
                    )
                )
            else:
                for line_no, row in _table_data_rows(ac_table):
                    if method_col >= len(row):
                        continue
                    method_cell = row[method_col].strip()
                    # Strip backticks/code formatting.
                    method_token = method_cell.strip("`").upper()
                    method_token = method_token.split()[0] if method_token else ""
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

    # ------------------------------------------------------------------
    # Decision Ledger semantic decision checks (DEC-001 / NUM-001 /
    # FALLBACK-001 / HARNESS-001)
    # ------------------------------------------------------------------
    decision_text = _semantic_decision_text(text)
    decision_table = find_table_under_section(text, "Decision Ledger")
    decision_table_missing_or_incomplete = (
        decision_table is None
        or bool(_missing_decision_ledger_headers(decision_table))
        or not _table_data_rows(decision_table)
    )
    if _DECISION_TRIGGER_RE.search(decision_text) and decision_table_missing_or_incomplete:
        detail = (
            "missing `Decision Ledger` section"
            if decision_table is None
            else "`Decision Ledger` has missing headers or no data rows"
        )
        findings.append(
            Finding(
                "DEC-001",
                SEVERITY_MEDIUM,
                (
                    "plan contains semantic decision triggers "
                    "(fallback/threshold/matcher/test harness) but has "
                    f"{detail}"
                ),
                plan.path,
                1 if decision_table is None else decision_table.start_line,
            )
        )

    if _NUMERIC_DECISION_TRIGGER_RE.search(decision_text) and not (
        decision_table
        and _decision_row_satisfies(
            decision_table,
            _NUMERIC_DECISION_TRIGGER_RE,
            ("rationale", "verification"),
        )
    ):
        findings.append(
            Finding(
                "NUM-001",
                SEVERITY_MEDIUM,
                (
                    "threshold/timeout/limit decisions must have a "
                    "`Decision Ledger` row with rationale and verification"
                ),
                plan.path,
                1 if decision_table is None else decision_table.start_line,
            )
        )

    if _FALLBACK_DECISION_TRIGGER_RE.search(decision_text) and not (
        decision_table
        and _decision_row_satisfies(
            decision_table,
            _FALLBACK_DECISION_TRIGGER_RE,
            ("caller.impact",),
        )
    ):
        findings.append(
            Finding(
                "FALLBACK-001",
                SEVERITY_MEDIUM,
                (
                    "fallback/empty/null/degraded behavior must have a "
                    "`Decision Ledger` row with caller/user impact"
                ),
                plan.path,
                1 if decision_table is None else decision_table.start_line,
            )
        )

    if _HARNESS_DECISION_TRIGGER_RE.search(decision_text) and not (
        decision_table
        and _decision_row_satisfies(
            decision_table,
            _HARNESS_DECISION_TRIGGER_RE,
            ("chosen.behavior", "verification"),
        )
    ):
        findings.append(
            Finding(
                "HARNESS-001",
                SEVERITY_MEDIUM,
                (
                    "mock/stub/fake-timer/content-script test harness decisions "
                    "must have a `Decision Ledger` row with setup details and verification"
                ),
                plan.path,
                1 if decision_table is None else decision_table.start_line,
            )
        )

    # ------------------------------------------------------------------
    # Contract Value Table conditional check (CVT-001 / CVT-002 / CVT-003)
    # ------------------------------------------------------------------
    contract_table = find_table_under_section(text, "Contract Value Table")
    if _contract_value_table_required(text):
        if contract_table is None:
            findings.append(
                Finding(
                    "CVT-001",
                    SEVERITY_MEDIUM,
                    (
                        "plan adds/changes contract literals but has no "
                        "`Contract Value Table` section"
                    ),
                    plan.path,
                    1,
                )
            )
        else:
            missing_headers = _missing_contract_value_headers(contract_table)
            if missing_headers:
                findings.append(
                    Finding(
                        "CVT-002",
                        SEVERITY_MEDIUM,
                        (
                            "`Contract Value Table` is missing required "
                            f"headers: {', '.join(missing_headers)}"
                        ),
                        plan.path,
                        contract_table.start_line,
                    )
                )
    if contract_table is not None and _cvt_rows_look_preserved_only(contract_table):
        findings.append(
            Finding(
                "CVT-003",
                SEVERITY_MEDIUM,
                (
                    "`Contract Value Table` appears to list only preserved or "
                    "unchanged literals; move unchanged invariants to "
                    "`Existing Behaviors Preserved` or `Decision Ledger`"
                ),
                plan.path,
                contract_table.start_line,
            )
        )

    # ------------------------------------------------------------------
    # Compatibility Matrix conditional check (COMPAT-001 / COMPAT-002)
    # ------------------------------------------------------------------
    boundary_groups = _boundary_groups_in_affected_areas(text)
    if len(boundary_groups) >= 2:
        compatibility_table = find_table_under_section(text, "Compatibility Matrix")
        if compatibility_table is None:
            findings.append(
                Finding(
                    "COMPAT-001",
                    SEVERITY_MEDIUM,
                    (
                        "Affected Areas spans separate lifecycle boundaries "
                        f"({', '.join(boundary_groups)}) but has no "
                        "`Compatibility Matrix` section"
                    ),
                    plan.path,
                    1,
                )
            )
        else:
            missing_scenarios = _missing_compat_scenarios(compatibility_table)
            if missing_scenarios:
                findings.append(
                    Finding(
                        "COMPAT-002",
                        SEVERITY_MEDIUM,
                        (
                            "`Compatibility Matrix` is missing scenarios: "
                            f"{', '.join(missing_scenarios)}"
                        ),
                        plan.path,
                        compatibility_table.start_line,
                    )
                )

    # ------------------------------------------------------------------
    # Test Delta conditional check (TEST-001 / TEST-002)
    # ------------------------------------------------------------------
    test_delta_table = find_table_under_section(text, "Test Delta")
    if _test_delta_required(text):
        if test_delta_table is None:
            findings.append(
                Finding(
                    "TEST-001",
                    SEVERITY_MEDIUM,
                    "plan changes test coverage but has no `Test Delta` table",
                    plan.path,
                    1,
                )
            )
        else:
            missing_headers = _missing_test_delta_headers(test_delta_table)
            data_rows = _table_data_rows(test_delta_table)
            if missing_headers or not data_rows:
                detail = (
                    f"missing headers: {', '.join(missing_headers)}"
                    if missing_headers
                    else "table has no data rows"
                )
                findings.append(
                    Finding(
                        "TEST-001",
                        SEVERITY_MEDIUM,
                        f"`Test Delta` is incomplete: {detail}",
                        plan.path,
                        test_delta_table.start_line,
                    )
                )
            else:
                action_col = _find_header(test_delta_table.rows[0], "action")
                if action_col is not None:
                    for line_no, row in data_rows:
                        if action_col >= len(row):
                            continue
                        action = row[action_col].strip().strip("`").upper()
                        if action not in {"KEEP", "UPDATE", "ADD"}:
                            findings.append(
                                Finding(
                                    "TEST-002",
                                    SEVERITY_MEDIUM,
                                    (
                                        "`Test Delta` action must be KEEP, "
                                        f"UPDATE, or ADD; got {row[action_col]!r}"
                                    ),
                                    plan.path,
                                    line_no,
                                )
                            )

    # ------------------------------------------------------------------
    # Risks require mitigation (RISK-001)
    # ------------------------------------------------------------------
    risk_body = section_body_lines(text, "Risks")
    for line_no, line in risk_body:
        stripped = line.lstrip()
        if not stripped.startswith(("-", "*", "+")):
            continue
        bullet = stripped[1:].strip()
        if not bullet:
            continue
        if bullet.lower().rstrip(".") in _EMPTY_BEHAVIOR_MARKERS:
            continue
        if not _RISK_MITIGATION_RE.search(bullet):
            findings.append(
                Finding(
                    "RISK-001",
                    SEVERITY_MEDIUM,
                    "risk bullet must include a `Mitigation:` clause",
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
