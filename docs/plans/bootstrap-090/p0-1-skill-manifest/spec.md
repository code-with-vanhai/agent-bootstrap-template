# Spec: Skill Manifest + Docs Drift Detection (P0-1)

**Status:** Verified with evidence: agent-validate.sh @ 2026-04-29T03:39:37Z (exit=0)
**Date:** 2026-04-29
**Ref commit:** `303546c`
**Plan location note:** Stored under `docs/plans/bootstrap-090/p0-1-skill-manifest/` because this template repo dogfoods plans under `docs/plans/`, not `.agent/runs/`. Generated target repos should use `.agent/runs/<date>-<slug>/`. `scripts/agent-validate-plan.sh` is intentionally not gating this artifact at draft time; once plan moves to `Proposed`, the validator may be invoked manually to surface findings.
**Track:** 0.9.0 → P0-1 of four locked P0 items (P0-1, P0-2, P0-3, P0-4).

---

## Problem

The template self-validator hard-codes the skill list in two places.



```python
EXPECTED_SKILLS = (
    "verify-before-completion",
    "root-cause-debugging",
    "scoped-implementation",
    "plan-before-code",
    "worktree-isolation",
    "no-invented-artifacts",
    "bootstrap-agent-system",
    "no-secret-leakage",
)
```





```python
        skill_files = list((self.root / "core/skills").glob("*/SKILL.md"))
        if len(skill_files) == 8:
            self.pass_("core/skills contains 8 skill files", "core/skills")
        else:
            self.fail(f"core/skills contains {len(skill_files)} skill files, expected 8", "core/skills")
```



Adding a skill currently requires editing both the Python tuple and the literal `== 8`. The 0.3.0 → 0.4.0 history shows this brittleness once already (count went 7 → 8 when `no-secret-leakage` was added). The same drift exposure is present in user-facing docs:



```text
- Seven optional native behavior skills: verify-before-completion, root-cause-debugging, scoped-implementation, plan-before-code, worktree-isolation, no-invented-artifacts, and bootstrap-agent-system.
```



`README.md:44` still says "Seven" even though `core/skills/` contains 8 directories and `no-secret-leakage` shipped in 0.8.0. The validator does not catch this docs drift today.

## Goal

Move the skill inventory to a single declarative source (`core/skills/manifest.json`), make `validate_agent_system.py` read that manifest in template-mode validation only, and add docs-drift checks for `README.md`, `USAGE.md`, and `core/skills/README.md`. Adding skill #9 in P1-3 (`data-safety`) must be a one-file change in the manifest plus the new skill directory; no validator edit, no README hand-edit beyond the manifest-derived count.

## Non-Goals

- Do not change `core/skills/<name>/SKILL.md` content.
- Do not change generated-mode validation behavior. Target repos do not have `core/skills/` and must continue to validate without it.
- Do not delete `EXPECTED_SKILLS` references outside `validate_agent_system.py`. (Verified by `Grep` at ref `303546c`: the tuple is only referenced at lines 19 and 288 in that file.)
- Do not modify `CHANGELOG.md` historical entries; immutable history, drift detection scope excludes it.
- Do not add a generated-repo skill manifest. P0-1 only governs the template repo's self-check.

## Affected Areas


| Area                            | Path                                             | Change                                                                                                   |
| ------------------------------- | ------------------------------------------------ | -------------------------------------------------------------------------------------------------------- |
| Template self-validator         | `scripts/lib/validate_agent_system.py`           | Replace tuple + count check with manifest load (template-mode only)                                      |
| Skill inventory source of truth | `core/skills/manifest.json` (new)                | Declarative skill list                                                                                   |
| README skill count              | `README.md:44`                                   | "Seven" → "8"                                                                                            |
| Validator unit tests            | `scripts/lib/test_validate_agent_system.py`      | Add 5 cases (manifest missing, mismatch, README drift, generated-mode no-op, README-skills numeric form) |
| Docs drift scope                | `README.md`, `USAGE.md`, `core/skills/README.md` | Validator scans for word-form skill counts                                                               |


## Acceptance Criteria


| ID    | Criterion                                                                                                            | Verification Method     | Gate                                                         |
| ----- | -------------------------------------------------------------------------------------------------------------------- | ----------------------- | ------------------------------------------------------------ |
| AC-1  | `core/skills/manifest.json` exists, parses as JSON, has `schema_version: 1` and `skills` array                       | `AUTOMATED-UNIT`        | `python3 -m unittest scripts.lib.test_validate_agent_system` |
| AC-2  | `validate_template()` loads skill list from `manifest.json`; module-level `EXPECTED_SKILLS` removed                  | `AUTOMATED-UNIT`        | same                                                         |
| AC-3  | Validator FAIL when `core/skills/<name>/` exists but name absent from manifest                                       | `AUTOMATED-UNIT`        | same                                                         |
| AC-4  | Validator FAIL when manifest references a skill whose `SKILL.md` is missing                                          | `AUTOMATED-UNIT`        | same                                                         |
| AC-5  | Validator FAIL on word-form skill count (`Seven`/`Eight`/...) in `README.md`, `USAGE.md`, or `core/skills/README.md` | `AUTOMATED-UNIT`        | same                                                         |
| AC-6  | Validator FAIL when numeric skill count in those 3 files mismatches `len(manifest.skills)`                           | `AUTOMATED-UNIT`        | same                                                         |
| AC-7  | Generated-mode validation runs cleanly with no `core/skills/` present (no exception, no manifest read attempt)       | `AUTOMATED-UNIT`        | same                                                         |
| AC-8  | `bash scripts/agent-validate.sh` (template mode against this repo) PASSes after change                               | `AUTOMATED-INTEGRATION` | `scripts/agent-validate.sh`                                  |
| AC-9  | All existing 75/75 Python unit tests in `scripts/lib/test_validate_agent_system.py` continue to pass                 | `AUTOMATED-UNIT`        | `python3 -m unittest scripts.lib.test_validate_agent_system` |
| AC-10 | `bash scripts/agent-evals.sh --fast` continues to PASS (no regression in deterministic eval set)                     | `AUTOMATED-INTEGRATION` | `scripts/agent-evals.sh --fast`                              |


## Public Contract Impact

- `core/skills/manifest.json` is a new internal contract. Schema v1: `{"schema_version": 1, "skills": [string, ...]}`. Adding fields in v2 must keep `schema_version` and `skills` shape backward compatible or bump version.
- No `.agent/manifest.json` change in target repos.
- No migration `core/migrations/0.9.0/migration.json` content change for this single P0-1 item; the migration manifest will accumulate other P0/P1 items before 0.9.0 ships. P0-1 alone touches only template-source files.

## Gate Choice

- Primary: `bash scripts/agent-validate.sh` (template-mode self-check) + `python3 -m unittest scripts.lib.test_validate_agent_system`.
- Auxiliary: `bash scripts/agent-evals.sh --fast` to confirm no regression in deterministic evals.
- Not applicable: `--behavior` and `--integration` eval modes (LLM-driven, advisory only). `agent-validate-plan.sh` not used as a gate; it would SKIP because no `.agent/manifest.json` synced version is present in the template repo root.

## Out-of-Scope (will be separate plans)


| P0/P1 | Item                                                                           | Plan path                                            |
| ----- | ------------------------------------------------------------------------------ | ---------------------------------------------------- |
| P0-2  | Native `.claude/agents/<role>.md` generation                                   | `docs/plans/bootstrap-090/p0-2-claude-subagents/`    |
| P0-3  | PreToolUse secret-guard hook (Python executable, not heredoc)                  | `docs/plans/bootstrap-090/p0-3-secret-guard-hook/`   |
| P0-4  | Adapter tier-list + generated-mode adapter validator                           | `docs/plans/bootstrap-090/p0-4-adapter-tier-list/`   |
| P1-1  | Candidate gate insertion in `agent-eval.sh`                                    | `docs/plans/bootstrap-090/p1-1-candidate-gates/`     |
| P1-2  | Migration walker (temp-clone phase 1)                                          | `docs/plans/bootstrap-090/p1-2-migration-walker/`    |
| P1-3  | Data Surface + `data-safety` skill (will use the manifest mechanism from P0-1) | `docs/plans/bootstrap-090/p1-3-data-surface/`        |
| P1-4  | `.agent/audit-log.jsonl` (no target `.gitignore` mutation)                     | `docs/plans/bootstrap-090/p1-4-audit-log/`           |
| P1-5  | `agent-validate-plan.sh --format json`                                         | `docs/plans/bootstrap-090/p1-5-plan-validator-json/` |

