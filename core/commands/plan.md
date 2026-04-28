---
description: Create a scoped spec and implementation plan before making code changes.
argument-hint: <task description>
---

# Plan

Read `.agent/rulebase.md`, `.agent/project-profile.md`, `.agent/ownership.md`, `.agent/gates.md`, `.agent/decisions.md`, and relevant `.agent/workflows/`.

Task: $ARGUMENTS

If invoked as `agent:plan <desc>` in a non-Claude harness, treat the text after `agent:plan` as the task description.

Follow `.agent/workflows/feature-workflow.md`, but execute planning only:

1. Define the goal, affected areas, owner, acceptance criteria, and verification gate.
2. For non-trivial work, create `.agent/runs/<date>-<slug>/spec.md` and `.agent/runs/<date>-<slug>/plan.md`.
3. For trivial work, write the plan inline only if it meets the repo's trivial-change rule.
4. Use only gates documented in `.agent/gates.md` and `scripts/agent-eval.sh`.
5. Stop before editing product code.

If the task is ambiguous enough that a plan would be speculative, ask one concise clarification question.

## Grounding Requirements

Before quoting any current code (BEFORE / Existing / Current snippet), you MUST:

1. Re-read the cited file in this same planning turn. Earlier session memory is not sufficient.
2. Quote using the evidence block format defined in `.agent/workflows/feature-workflow.md` (`current-code` HTML comment delimiters with `path`, `lines`, `ref`, and `region_sha256`).
3. If the assumed pattern (`className`, import, function name, line range) is not present in the working tree, STOP and revise the plan goal — do not fabricate a snippet that fits the proposed AFTER.
4. List every modified function in an `Existing Behaviors Preserved` section with evidence-block citations and classification (`PRESERVED`, `INTENTIONALLY REMOVED`, or `BUG FIX`).
5. Classify every acceptance criterion with a Verification Method enum value (`AUTOMATED-UNIT`, `AUTOMATED-INTEGRATION`, `AUTOMATED-E2E`, `BUILD-OUTPUT`, `TYPECHECK`, `MANUAL`). Behaviors that depend on real layout APIs cannot be `AUTOMATED-UNIT` in jsdom.
6. Use `Status: Draft` or `Status: Proposed` only. Do not self-assign quality scores or `Ready` checkmarks; status is upgraded to `Verified with evidence: <gate> @ <UTC> (exit=<code>)` only after a fresh gate run.
7. Include an `Implementation Plan` section with concrete steps. Do not leave behavior-affecting choices as `consider`, `maybe`, `could`, `or add`, or similar hedges.
8. If an `Open Questions` section is present, each `- Q:` bullet must be followed by `- RESOLVED:` or `- DEFERRED:`.
9. If adding enum/status/error-code/message literals, include a literal mapping table and cite the existing naming convention with an evidence block.
10. If touching separate lifecycle boundaries, include a `Compatibility Matrix` section. If adding/updating/keeping tests, include a `Test Delta` section.
11. Every non-empty `Risks` bullet must include `Mitigation:`.

A plan that quotes non-existent code or omits the sections above is rejected at review, regardless of how sensible the AFTER section is. The repo's `scripts/agent-validate-plan.sh` enforces these requirements mechanically when present.
