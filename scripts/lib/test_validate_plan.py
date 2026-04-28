"""Stdlib unittest for scripts/lib/validate_plan.py.

Run from the template root with:

    python3 -m unittest scripts.lib.test_validate_plan
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

# Allow running both as ``python3 -m unittest scripts.lib.test_validate_plan``
# and as ``python3 scripts/lib/test_validate_plan.py``.
import sys
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from lib import validate_plan  # type: ignore  # noqa: E402


def _sha256_normalized(text: str) -> str:
    return hashlib.sha256(validate_plan.normalize_whitespace(text).encode("utf-8")).hexdigest()


class TempRepo:
    def __init__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="validate-plan-test-"))
        self._init_git()
        # Skeleton .agent so detect_repo_root finds it deterministically.
        (self.tmp / ".agent").mkdir(exist_ok=True)
        (self.tmp / ".agent" / "manifest.json").write_text("{}", encoding="utf-8")

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, rel: str, content: str):
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def commit_all(self, message: str = "fixture") -> str:
        subprocess.run(
            ["git", "-C", str(self.tmp), "add", "."],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["git", "-C", str(self.tmp), "-c", "user.email=t@t", "-c", "user.name=Test",
             "commit", "-q", "-m", message],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        out = subprocess.run(
            ["git", "-C", str(self.tmp), "rev-parse", "--short=10", "HEAD"],
            check=True, stdout=subprocess.PIPE,
        ).stdout.decode().strip()
        return out

    def _init_git(self):
        subprocess.run(
            ["git", "init", "-q", str(self.tmp)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )


def _make_evidence_block(path: str, lines: str, ref: str, snippet: str) -> str:
    sha = _sha256_normalized(snippet)
    return (
        f"<!-- current-code path={path} lines={lines} ref={ref} region_sha256={sha} -->\n"
        f"```text\n{snippet}\n```\n"
        f"<!-- /current-code -->\n"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class WhitespaceNormalizeTest(unittest.TestCase):
    def test_collapse_and_strip(self):
        self.assertEqual(
            validate_plan.normalize_whitespace("  a   b\n\n  c  \n"),
            "a b c",
        )


class EvidenceBlockTest(unittest.TestCase):
    def setUp(self):
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)
        self.target_path = self.repo.write("src/app.ts", "first line\nsecond line\nthird line\n")
        self.ref = self.repo.commit_all("baseline")

    def _plan_with(self, blocks: str, sections: bool = True) -> str:
        sections_md = ""
        if sections:
            sections_md = textwrap.dedent(
                """\
                ## Implementation Plan

                - Apply the decided change.

                ## Acceptance Criteria

                | # | Criterion | Verification Method |
                |---|---|---|
                | 1 | works | `AUTOMATED-UNIT` |

                ## Existing Behaviors Preserved

                - none

                ## Verification

                ```bash
                npm run typecheck
                ```
                """
            )
        return f"# Plan\n\n{blocks}\n{sections_md}"

    def test_grounded_block_passes(self):
        block = _make_evidence_block("src/app.ts", "1-1", self.ref, "first line")
        plan = self.repo.write(".agent/runs/x/plan.md", self._plan_with(block))
        ctx = validate_plan.detect_repo_context(self.repo.tmp)
        findings = validate_plan.validate_plan(
            validate_plan.PlanFile(plan, plan.read_text()),
            ctx,
            strict=False,
        )
        ev_high = [f for f in findings if f.check_id.startswith("EV-") and f.severity == "High"]
        self.assertEqual(ev_high, [], f"unexpected High findings: {ev_high}")

    def test_snippet_mismatch_flags_ev003(self):
        sha = _sha256_normalized("WRONG TEXT")
        block = (
            f"<!-- current-code path=src/app.ts lines=1-1 ref={self.ref} "
            f"region_sha256={sha} -->\n"
            "```text\nWRONG TEXT\n```\n"
            "<!-- /current-code -->\n"
        )
        plan = self.repo.write(".agent/runs/x/plan.md", self._plan_with(block))
        ctx = validate_plan.detect_repo_context(self.repo.tmp)
        findings = validate_plan.validate_plan(
            validate_plan.PlanFile(plan, plan.read_text()),
            ctx,
            strict=False,
        )
        codes = {f.check_id for f in findings}
        self.assertIn("EV-003", codes)

    def test_path_traversal_flags_ev002(self):
        block = (
            "<!-- current-code path=../etc/passwd lines=1-1 ref=abcdef0 "
            "region_sha256=" + _sha256_normalized("x") + " -->\n"
            "```text\nx\n```\n"
            "<!-- /current-code -->\n"
        )
        plan = self.repo.write(".agent/runs/x/plan.md", self._plan_with(block))
        ctx = validate_plan.detect_repo_context(self.repo.tmp)
        findings = validate_plan.validate_plan(
            validate_plan.PlanFile(plan, plan.read_text()),
            ctx,
            strict=False,
        )
        codes = {f.check_id for f in findings}
        self.assertIn("EV-002", codes)

    def test_missing_attrs_flags_ev001(self):
        block = (
            "<!-- current-code path=src/app.ts lines=1-1 -->\n"
            "```text\nfirst line\n```\n"
            "<!-- /current-code -->\n"
        )
        plan = self.repo.write(".agent/runs/x/plan.md", self._plan_with(block))
        ctx = validate_plan.detect_repo_context(self.repo.tmp)
        findings = validate_plan.validate_plan(
            validate_plan.PlanFile(plan, plan.read_text()),
            ctx,
            strict=False,
        )
        codes = {f.check_id for f in findings}
        self.assertIn("EV-001", codes)

    def test_bad_sha_flags_ev005(self):
        block = (
            f"<!-- current-code path=src/app.ts lines=1-1 ref={self.ref} "
            "region_sha256=00deadbeef -->\n"
            "```text\nfirst line\n```\n"
            "<!-- /current-code -->\n"
        )
        plan = self.repo.write(".agent/runs/x/plan.md", self._plan_with(block))
        ctx = validate_plan.detect_repo_context(self.repo.tmp)
        findings = validate_plan.validate_plan(
            validate_plan.PlanFile(plan, plan.read_text()),
            ctx,
            strict=False,
        )
        codes = {f.check_id for f in findings}
        self.assertIn("EV-005", codes)


class SelfClaimTest(unittest.TestCase):
    def setUp(self):
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)

    def _ctx(self):
        return validate_plan.detect_repo_context(self.repo.tmp)

    def _validate(self, text: str):
        plan = self.repo.write(".agent/runs/y/plan.md", text)
        return validate_plan.validate_plan(
            validate_plan.PlanFile(plan, text), self._ctx(), strict=False
        )

    def test_quality_target_score_flagged(self):
        text = "## Plan\n\nQuality target: 9.5/10 ✅\n\n## Verification\n\nnone"
        codes = {f.check_id for f in self._validate(text)}
        self.assertIn("SC-001", codes)

    def test_status_ready_flagged(self):
        text = "## Plan\n\nStatus: Ready ✅\n\n## Verification\n\nnone"
        codes = {f.check_id for f in self._validate(text)}
        self.assertIn("SC-003", codes)

    def test_self_claim_inside_code_block_ignored(self):
        text = (
            "## Plan\n\n```\nQuality target: 9.5/10\n```\n\n## Verification\n\nnone"
        )
        codes = {f.check_id for f in self._validate(text)}
        self.assertNotIn("SC-001", codes)

    def test_verified_with_evidence_allowed(self):
        text = (
            "## Plan\n\nStatus: Verified with evidence: fast @ 2026-04-26T10:00Z (exit=0)\n"
            "Ready for merge\n\n## Verification\n\nnone"
        )
        codes = {f.check_id for f in self._validate(text)}
        self.assertNotIn("SC-004", codes)


class LintPackTest(unittest.TestCase):
    def setUp(self):
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)

    def _validate_with_pkg(self, react_version: str, mv3: bool, plan_text: str):
        pkg = {
            "name": "fixture",
            "dependencies": {"react": react_version},
        }
        if mv3:
            pkg["devDependencies"] = {"@types/chrome": "^0.0.300"}
        self.repo.write("package.json", json.dumps(pkg))
        plan = self.repo.write(".agent/runs/z/plan.md", plan_text)
        ctx = validate_plan.detect_repo_context(self.repo.tmp)
        return validate_plan.validate_plan(
            validate_plan.PlanFile(plan, plan_text),
            ctx,
            strict=False,
        ), ctx

    def test_contains_selector_flagged(self):
        text = (
            "## Plan\n\n```ts\ncontainer.querySelector('button:contains(\"Next\")');\n```"
            "\n\n## Verification\n\nnone"
        )
        findings, _ = self._validate_with_pkg("^18", False, text)
        codes = {f.check_id for f in findings}
        self.assertIn("LP-001", codes)

    def test_react_dom_test_utils_flagged_only_for_react19(self):
        text = (
            "## Plan\n\n```ts\nimport { act } from 'react-dom/test-utils';\n```"
            "\n\n## Verification\n\nnone"
        )
        f18, _ = self._validate_with_pkg("^18.2.0", False, text)
        f19, _ = self._validate_with_pkg("^19.0.0", False, text)
        self.assertNotIn("LP-002", {f.check_id for f in f18})
        self.assertIn("LP-002", {f.check_id for f in f19})

    def test_chrome_stub_flagged_only_for_mv3(self):
        text = (
            "## Plan\n\n```ts\nvi.stubGlobal('chrome', { runtime: { sendMessage: vi.fn() } });\n```"
            "\n\n## Verification\n\nnone"
        )
        non_mv3, _ = self._validate_with_pkg("^18", False, text)
        mv3, _ = self._validate_with_pkg("^18", True, text)
        self.assertNotIn("LP-003", {f.check_id for f in non_mv3})
        self.assertIn("LP-003", {f.check_id for f in mv3})


class BoldedSelfClaimTest(unittest.TestCase):
    """Regression coverage for the BrainMap dogfood: bold labels around the colon."""

    def setUp(self):
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)

    def _validate(self, body: str):
        text = "## Plan\n\n" + body + "\n\n## Verification\n\nnone\n"
        plan = self.repo.write(".agent/runs/b/plan.md", text)
        ctx = validate_plan.detect_repo_context(self.repo.tmp)
        return validate_plan.validate_plan(
            validate_plan.PlanFile(plan, text), ctx, strict=False
        )

    def test_bold_quality_target_flagged(self):
        codes = {f.check_id for f in self._validate("**Quality target:** 9.5/10 \u2705")}
        self.assertIn("SC-001", codes)

    def test_bold_status_ready_flagged(self):
        codes = {f.check_id for f in self._validate("**Status:** Ready for implementation")}
        self.assertIn("SC-003", codes)

    def test_backtick_score_flagged(self):
        codes = {f.check_id for f in self._validate("`Score:` 7/10")}
        self.assertIn("SC-002", codes)


class BehaviorPreservedTest(unittest.TestCase):
    def setUp(self):
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)

    def _validate(self, behavior_section: str, evidence_block: str = "") -> list:
        text = textwrap.dedent(
            """\
            # Plan

            ## Implementation Plan

            - Apply the decided change.

            ## Acceptance Criteria

            | # | Criterion | Verification Method |
            |---|---|---|
            | 1 | works | `MANUAL` |

            {evidence}

            ## Existing Behaviors Preserved

            {behavior}

            ## Verification

            ```bash
            none
            ```
            """
        ).format(evidence=evidence_block, behavior=behavior_section)
        plan = self.repo.write(".agent/runs/x/plan.md", text)
        ctx = validate_plan.detect_repo_context(self.repo.tmp)
        return validate_plan.validate_plan(
            validate_plan.PlanFile(plan, text), ctx, strict=False
        )

    def test_none_marker_does_not_require_citation(self):
        codes = {f.check_id for f in self._validate("- none")}
        self.assertNotIn("BEH-001", codes)
        self.assertNotIn("BEH-002", codes)

    def test_real_bullet_without_evidence_block_flags_beh001(self):
        codes = {f.check_id for f in self._validate(
            "- handler emits an analytics event before redirecting"
        )}
        self.assertIn("BEH-001", codes)

    def test_real_bullet_with_evidence_block_no_inline_cite_flags_beh002_only(self):
        # Provide an evidence block somewhere so BEH-001 does not fire, but
        # the bullet itself has no inline citation token.
        self.repo.write("src/x.ts", "console.log(1)\nconsole.log(2)\n")
        evidence = (
            "<!-- current-code path=src/x.ts lines=1-1 ref=deadbeef "
            "region_sha256=" + _sha256_normalized("console.log(1)") + " -->\n"
            "```ts\nconsole.log(1)\n```\n"
            "<!-- /current-code -->\n"
        )
        findings = self._validate(
            "- handler emits an analytics event before redirecting",
            evidence_block=evidence,
        )
        codes = {f.check_id for f in findings}
        self.assertNotIn("BEH-001", codes)
        self.assertIn("BEH-002", codes)

    def test_bullet_with_inline_citation_passes(self):
        self.repo.write("src/x.ts", "console.log(1)\n")
        evidence = (
            "<!-- current-code path=src/x.ts lines=1-1 ref=deadbeef "
            "region_sha256=" + _sha256_normalized("console.log(1)") + " -->\n"
            "```ts\nconsole.log(1)\n```\n"
            "<!-- /current-code -->\n"
        )
        findings = self._validate(
            "- handler emits an analytics event (`src/x.ts:1-1`) before redirect",
            evidence_block=evidence,
        )
        codes = {f.check_id for f in findings}
        self.assertNotIn("BEH-001", codes)
        self.assertNotIn("BEH-002", codes)


class TargetVersionSkipTest(unittest.TestCase):
    """Validator must skip when target repo synced version is < 0.4.0."""

    def setUp(self):
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)

    def _write_manifest(self, version: str):
        path = self.repo.tmp / ".agent" / "manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"synced_to_template_version": version}),
            encoding="utf-8",
        )

    def _write_plan_with_high_findings(self) -> Path:
        text = "# Plan\n\n(missing required sections)\n"
        return self.repo.write(".agent/runs/x/plan.md", text)

    def test_old_version_skips(self):
        self._write_manifest("0.3.0")
        plan = self._write_plan_with_high_findings()
        rc = validate_plan.main([str(plan), "--repo-root", str(self.repo.tmp)])
        self.assertEqual(rc, 0)

    def test_force_flag_overrides(self):
        self._write_manifest("0.3.0")
        plan = self._write_plan_with_high_findings()
        rc = validate_plan.main([str(plan), "--repo-root", str(self.repo.tmp), "--force"])
        self.assertEqual(rc, 1)

    def test_current_version_validates(self):
        self._write_manifest("0.4.0")
        plan = self._write_plan_with_high_findings()
        rc = validate_plan.main([str(plan), "--repo-root", str(self.repo.tmp)])
        self.assertEqual(rc, 1)


class TripleBacktickSnippetTest(unittest.TestCase):
    """Evidence snippets containing inner triple-backticks must round-trip."""

    def setUp(self):
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)

    def test_inner_fence_preserved_via_outer_fence_of_higher_width(self):
        # Source file content contains a triple-backtick line.
        snippet = "```ts\nconsole.log(1)\n```"
        self.repo.write("src/code.md", snippet + "\n")
        ref = self.repo.commit_all("with fence content")

        sha = _sha256_normalized(snippet)
        # Use a quad-backtick outer fence to wrap a snippet with inner ```ts.
        block = (
            f"<!-- current-code path=src/code.md lines=1-3 ref={ref} "
            f"region_sha256={sha} -->\n"
            "````md\n"
            f"{snippet}\n"
            "````\n"
            "<!-- /current-code -->\n"
        )
        text = textwrap.dedent(
            """\
            # Plan

            {block}

            ## Implementation Plan

            - Apply the decided change.

            ## Acceptance Criteria

            | # | Criterion | Verification Method |
            |---|---|---|
            | 1 | x | `MANUAL` |

            ## Existing Behaviors Preserved

            - none

            ## Verification

            ```bash
            none
            ```
            """
        ).format(block=block)
        plan = self.repo.write(".agent/runs/x/plan.md", text)
        ctx = validate_plan.detect_repo_context(self.repo.tmp)
        findings = validate_plan.validate_plan(
            validate_plan.PlanFile(plan, text), ctx, strict=False
        )
        ev_high = [f for f in findings if f.check_id.startswith("EV-") and f.severity == "High"]
        self.assertEqual(ev_high, [], f"unexpected High EV findings: {ev_high}")


class SectionsAndAcTest(unittest.TestCase):
    def setUp(self):
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)

    def _ctx(self):
        return validate_plan.detect_repo_context(self.repo.tmp)

    def test_missing_sections_flag_sect001(self):
        text = "# Plan\n\nGoal: do a thing.\n"
        plan = self.repo.write(".agent/runs/m/plan.md", text)
        findings = validate_plan.validate_plan(
            validate_plan.PlanFile(plan, text), self._ctx(), strict=False,
        )
        codes = {f.check_id for f in findings}
        self.assertIn("SECT-001", codes)

    def test_unknown_method_flags_ac001(self):
        text = textwrap.dedent(
            """\
            # Plan

            ## Implementation Plan

            - Apply the decided change.

            ## Acceptance Criteria

            | # | Criterion | Verification Method |
            |---|---|---|
            | 1 | does the thing | `WishfulThinking` |

            ## Existing Behaviors Preserved

            - none

            ## Verification

            ```bash
            ok
            ```
            """
        )
        plan = self.repo.write(".agent/runs/m/plan.md", text)
        findings = validate_plan.validate_plan(
            validate_plan.PlanFile(plan, text), self._ctx(), strict=False,
        )
        codes = {f.check_id for f in findings}
        self.assertIn("AC-001", codes)

    def test_layout_dependent_unit_flags_ac002(self):
        text = textwrap.dedent(
            """\
            # Plan

            ## Implementation Plan

            - Apply the decided change.

            ## Acceptance Criteria

            | # | Criterion | Verification Method |
            |---|---|---|
            | 1 | scrollTop preserves position after navigation | `AUTOMATED-UNIT` |

            ## Existing Behaviors Preserved

            - none

            ## Verification

            ```bash
            ok
            ```
            """
        )
        plan = self.repo.write(".agent/runs/m/plan.md", text)
        findings = validate_plan.validate_plan(
            validate_plan.PlanFile(plan, text), self._ctx(), strict=False,
        )
        codes = {f.check_id for f in findings}
        self.assertIn("AC-002", codes)


class DecisionCompletenessTest(unittest.TestCase):
    def setUp(self):
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)

    def _ctx(self):
        return validate_plan.detect_repo_context(self.repo.tmp)

    def _validate(
        self,
        *,
        status: str = "Proposed",
        implementation: str = "- Apply the decided change.",
        open_questions: str = "",
        ac_row: str = "| 1 | works | `MANUAL` |",
    ) -> list:
        open_questions_section = ""
        if open_questions:
            open_questions_section = (
                "\n## Open Questions\n\n" + open_questions.rstrip() + "\n"
            )
        text = textwrap.dedent(
            f"""\
            # Plan

            **Status:** {status}

            ## Implementation Plan

            {implementation}
            {open_questions_section}
            ## Acceptance Criteria

            | # | Criterion | Verification Method |
            |---|---|---|
            {ac_row}

            ## Existing Behaviors Preserved

            - none

            ## Verification

            ```bash
            ok
            ```
            """
        )
        plan = self.repo.write(".agent/runs/d/plan.md", text)
        return validate_plan.validate_plan(
            validate_plan.PlanFile(plan, text), self._ctx(), strict=False,
        )

    def test_open_questions_absent_does_not_flag_oq001(self):
        codes = {f.check_id for f in self._validate()}
        self.assertNotIn("OQ-001", codes)

    def test_open_question_with_resolution_passes(self):
        codes = {
            f.check_id
            for f in self._validate(
                open_questions=(
                    "- Q: Which field owns the code?\n"
                    "  - RESOLVED: `SAVE_ERROR.code` owns it."
                )
            )
        }
        self.assertNotIn("OQ-001", codes)

    def test_unresolved_open_question_is_medium_in_draft(self):
        findings = self._validate(
            status="Draft",
            open_questions="- Q: Which field owns the code?",
        )
        oq = [f for f in findings if f.check_id == "OQ-001"]
        self.assertEqual([f.severity for f in oq], ["Medium"])

    def test_unresolved_open_question_is_high_in_proposed(self):
        findings = self._validate(open_questions="- Q: Which field owns the code?")
        oq = [f for f in findings if f.check_id == "OQ-001"]
        self.assertEqual([f.severity for f in oq], ["High"])

    def test_hedged_implementation_bullet_flags_impl001(self):
        codes = {
            f.check_id
            for f in self._validate(implementation="- Consider adding a fallback mapper.")
        }
        self.assertIn("IMPL-001", codes)

    def test_non_hedged_implementation_bullet_passes_impl001(self):
        codes = {
            f.check_id
            for f in self._validate(
                implementation="- Handle the case where the fallback mapper receives an unknown code."
            )
        }
        self.assertNotIn("IMPL-001", codes)

    def test_consider_the_case_wording_passes_impl001(self):
        codes = {
            f.check_id
            for f in self._validate(
                implementation="- Consider the case where the mapper receives an unknown code."
            )
        }
        self.assertNotIn("IMPL-001", codes)

    def test_ac_code_or_status_needs_literal_target(self):
        codes = {
            f.check_id
            for f in self._validate(
                ac_row="| 1 | emits a stable code for no active tab | `AUTOMATED-UNIT` |"
            )
        }
        self.assertIn("AC-003", codes)

    def test_ac_code_literal_target_passes_ac003(self):
        codes = {
            f.check_id
            for f in self._validate(
                ac_row="| 1 | emits stable code `NO_ACTIVE_TAB` for no active tab | `AUTOMATED-UNIT` |"
            )
        }
        self.assertNotIn("AC-003", codes)

    def test_ac_documentation_cannot_be_typecheck_only(self):
        codes = {
            f.check_id
            for f in self._validate(
                ac_row="| 1 | documents the error-code union comment | `TYPECHECK` |"
            )
        }
        self.assertIn("AC-004", codes)


class ConditionalTableChecksTest(unittest.TestCase):
    def setUp(self):
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)

    def _ctx(self):
        return validate_plan.detect_repo_context(self.repo.tmp)

    def _validate(
        self,
        *,
        affected_areas: str = "- shared helper",
        implementation: str = "- Apply the decided change.",
        ac_row: str = "| 1 | works | `MANUAL` |",
        extra_sections: str = "",
        risks: str = "- none",
    ) -> list:
        text = (
            "# Plan\n\n"
            "**Status:** Proposed\n\n"
            "## Affected Areas\n\n"
            f"{affected_areas}\n\n"
            "## Implementation Plan\n\n"
            f"{implementation}\n\n"
            "## Acceptance Criteria\n\n"
            "| # | Criterion | Verification Method |\n"
            "|---|---|---|\n"
            f"{ac_row}\n\n"
            "## Existing Behaviors Preserved\n\n"
            "- none\n\n"
            f"{extra_sections.strip()}\n\n"
            "## Risks\n\n"
            f"{risks}\n\n"
            "## Verification\n\n"
            "```bash\n"
            "ok\n"
            "```\n"
        )
        plan = self.repo.write(".agent/runs/c/plan.md", text)
        return validate_plan.validate_plan(
            validate_plan.PlanFile(plan, text), self._ctx(), strict=False,
        )

    def test_find_table_under_section_returns_custom_table(self):
        text = textwrap.dedent(
            """\
            # Plan

            ## Custom Table

            | Name | Value |
            |---|---|
            | a | b |

            ## Next

            | Other | Table |
            |---|---|
            | c | d |
            """
        )
        table = validate_plan.find_table_under_section(text, "Custom Table")
        self.assertIsNotNone(table)
        assert table is not None
        self.assertEqual(table.start_line, 5)
        self.assertEqual(table.rows[0], ["Name", "Value"])
        self.assertEqual(table.rows[2], ["a", "b"])

    def test_contract_literal_without_value_table_flags_cvt001(self):
        codes = {
            f.check_id
            for f in self._validate(
                ac_row=(
                    "| 1 | emits stable error code `NO_ACTIVE_TAB` "
                    "for no active tab | `AUTOMATED-UNIT` |"
                )
            )
        }
        self.assertIn("CVT-001", codes)

    def test_complete_contract_value_table_passes(self):
        extra = textwrap.dedent(
            """\
            ## Contract Value Table

            | Literal | Producer | Consumer | User-facing behavior | Test |
            |---|---|---|---|---|
            | `NO_ACTIVE_TAB` | `src/bg.ts` | `src/ui.tsx` | existing copy | `src/ui.test.tsx` |
            """
        )
        codes = {
            f.check_id
            for f in self._validate(
                ac_row=(
                    "| 1 | emits stable error code `NO_ACTIVE_TAB` "
                    "for no active tab | `AUTOMATED-UNIT` |"
                ),
                extra_sections=extra,
            )
        }
        self.assertNotIn("CVT-001", codes)
        self.assertNotIn("CVT-002", codes)

    def test_contract_value_table_missing_headers_flags_cvt002(self):
        extra = textwrap.dedent(
            """\
            ## Contract Value Table

            | Literal | Producer |
            |---|---|
            | `NO_ACTIVE_TAB` | `src/bg.ts` |
            """
        )
        codes = {
            f.check_id
            for f in self._validate(
                ac_row=(
                    "| 1 | emits stable error code `NO_ACTIVE_TAB` "
                    "for no active tab | `AUTOMATED-UNIT` |"
                ),
                extra_sections=extra,
            )
        }
        self.assertIn("CVT-002", codes)

    def test_cross_boundary_without_compat_matrix_flags_compat001(self):
        codes = {
            f.check_id
            for f in self._validate(
                affected_areas="- background handler\n- side panel UI"
            )
        }
        self.assertIn("COMPAT-001", codes)

    def test_compat_matrix_missing_scenarios_flags_compat002(self):
        extra = textwrap.dedent(
            """\
            ## Compatibility Matrix

            | Scenario | Behavior | Test |
            |---|---|---|
            | old producer + new consumer | fallback works | manual |
            """
        )
        codes = {
            f.check_id
            for f in self._validate(
                affected_areas="- background handler\n- side panel UI",
                extra_sections=extra,
            )
        }
        self.assertIn("COMPAT-002", codes)

    def test_complete_compat_matrix_passes(self):
        extra = textwrap.dedent(
            """\
            ## Compatibility Matrix

            | Scenario | Behavior | Test |
            |---|---|---|
            | old producer + new consumer | fallback works | manual |
            | new producer + old consumer | legacy string works | manual |
            | unknown value | fall through to fallback | unit |
            | empty value | fall through to fallback | unit |
            | missing field | fall through to fallback | unit |
            """
        )
        codes = {
            f.check_id
            for f in self._validate(
                affected_areas="- background handler\n- side panel UI",
                extra_sections=extra,
            )
        }
        self.assertNotIn("COMPAT-001", codes)
        self.assertNotIn("COMPAT-002", codes)

    def test_test_change_without_delta_flags_test001(self):
        codes = {
            f.check_id
            for f in self._validate(implementation="- Add tests for coded extraction.")
        }
        self.assertIn("TEST-001", codes)

    def test_test_delta_invalid_action_flags_test002(self):
        extra = textwrap.dedent(
            """\
            ## Test Delta

            | Test | Action | Why |
            |---|---|---|
            | `src/ui.test.tsx` | `MAYBE` | covers branch |
            """
        )
        codes = {
            f.check_id
            for f in self._validate(
                implementation="- Add tests for coded extraction.",
                extra_sections=extra,
            )
        }
        self.assertIn("TEST-002", codes)
        self.assertNotIn("CVT-001", codes)

    def test_complete_test_delta_passes(self):
        extra = textwrap.dedent(
            """\
            ## Test Delta

            | Test | Action | Why |
            |---|---|---|
            | `src/ui.test.tsx` | `ADD` | covers branch |
            """
        )
        codes = {
            f.check_id
            for f in self._validate(
                implementation="- Add tests for coded extraction.",
                extra_sections=extra,
            )
        }
        self.assertNotIn("TEST-001", codes)
        self.assertNotIn("TEST-002", codes)
        self.assertNotIn("CVT-001", codes)

    def test_risk_without_mitigation_flags_risk001(self):
        codes = {
            f.check_id
            for f in self._validate(risks="- Risk: rolling update mismatch.")
        }
        self.assertIn("RISK-001", codes)

    def test_risk_with_mitigation_passes(self):
        codes = {
            f.check_id
            for f in self._validate(
                risks="- Risk: rolling update mismatch. Mitigation: keep fallback."
            )
        }
        self.assertNotIn("RISK-001", codes)


if __name__ == "__main__":
    unittest.main()
