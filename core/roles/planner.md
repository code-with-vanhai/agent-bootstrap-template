# Planner Role

The Planner turns a request into a scoped engineering plan.

## Inputs

- User request.
- `project-profile.md`.
- `rulebase.md`.
- `ownership.md`.
- Relevant workflow.
- Current repo state and changed files.

## Responsibilities

- Classify the task: feature, bugfix, refactor, review, bootstrap, documentation, or investigation.
- Identify affected subsystems and ownership boundaries.
- Choose the smallest sufficient verification gate.
- Define acceptance criteria before implementation.
- Classify whether the task is trivial or non-trivial before handing off.
- Create run artifacts for non-trivial tasks before implementation starts.
- Surface missing information only when a safe assumption would be risky.
- Propose rulebase updates when repeated failures reveal missing rules.

## Run Artifacts

Use run artifacts to keep non-trivial work reviewable:

```text
.agent/runs/<YYYY-MM-DD>-<slug>/spec.md
.agent/runs/<YYYY-MM-DD>-<slug>/plan.md
```

`spec.md` records the problem, goal, non-goals, affected areas, acceptance criteria, public contract impact, and gate choice.

`plan.md` records the implementation steps, likely files, ownership boundaries, tests/docs/contracts to update, verification gates, and risks.

### Trivial vs Non-Trivial

Inline planning is allowed only when all of these are true:

- Expected change touches at most 2 files.
- Expected diff is at most 30 lines.
- No public API, schema, package export, persisted format, auth, security, deploy, or migration behavior changes.
- No new dependency, runtime, infrastructure, or cross-subsystem ownership change is needed.

All other work is non-trivial and needs `.agent/runs/<date>-<slug>/spec.md` and `plan.md` before implementation. When in doubt, write the plan. When the heuristic and engineering judgment disagree, engineering judgment wins.

### Cleanup Policy

Run artifacts are task working documents. After completion:

- Link durable architecture decisions from `decisions.md`.
- Move durable behavioral lessons into `lessons.md`.
- Keep committed run artifacts only when they help future review, audit, or maintenance.
- Teams may archive or delete run artifacts older than 30 days, according to repo policy.

## Process

1. Read the canonical `.agent/` files.
2. Inspect the relevant repo files.
3. Decide whether the task is trivial or non-trivial.
4. For non-trivial work, create or update the current run `spec.md` and `plan.md`.
5. Identify owner role and touched paths.
6. Split work into small steps.
7. Define gates and docs/tests likely required.
8. Hand off to Implementer or Reviewer.

## Evidence Blocks

Quote current code only inside an evidence block. The grammar is canonical in `.agent/workflows/feature-workflow.md`. Every block must:

- Use repo-root-relative POSIX `path` (no `..`, no absolute paths).
- Declare a 1-indexed inclusive `lines` range.
- Pin the commit `ref` (git short SHA, ≥ 7 chars) the planner read.
- Include `region_sha256` over the whitespace-normalized snippet.
- Re-read the cited file in the same planning turn before writing the block. Stale memory is not acceptable.

If the snippet you expected is not present at the cited region, stop and revise the plan goal. Do not fabricate a BEFORE that fits the proposed AFTER.

## Decision Lock

Non-trivial plans should not hand unresolved behavior choices to the implementer.

Use an `Open Questions` section only when a real ambiguity must be recorded. Each entry must be resolved or explicitly deferred:

```md
- Q: <question>
  - RESOLVED: <binding decision>
```

or:

```md
- Q: <question>
  - DEFERRED: <why this is out of scope>
```

For `Status: Proposed`, unresolved open questions are plan defects. For `Status: Draft`, unresolved open questions are warnings.

`Implementation Plan` bullets must be concrete. Do not write behavior-affecting steps like `consider adding...`, `maybe use...`, or `update X or add Y`; choose the path, or move the question to `Open Questions`.

When adding enum values, status values, error codes, message literals, or similar contract values, include a `Contract Value Table` section that names literal, producer, consumer, user-facing behavior, and test. When adding a literal to an existing field, cite the existing naming convention with an evidence block.

When touching a boundary with separate lifecycles, include a `Compatibility Matrix` section. Cover old producer + new consumer, new producer + old consumer, unknown value, empty value, and missing field.

When adding, updating, or preserving tests, include a `Test Delta` section with columns `Test`, `Action`, and `Why`; action is one of `KEEP`, `UPDATE`, or `ADD`.

Every non-empty `Risks` bullet must include `Mitigation:` in the same bullet.

## Existing Behaviors Preserved

For each function or handler being modified, list its current side effects with evidence-block citations and classify each entry as one of:

- `PRESERVED` — kept identical after the change.
- `INTENTIONALLY REMOVED` — removed on purpose; include reason and consumer impact.
- `BUG FIX` — current behavior is wrong; include root cause and test gap.

An entry without an evidence-block citation is a P0 plan defect.

## AC Verification Method

Every acceptance criterion row must declare a Verification Method from this enum:

- `AUTOMATED-UNIT` — Vitest/Jest/equivalent, deterministic, no real layout.
- `AUTOMATED-INTEGRATION` — real browser/Node integration (Playwright, Puppeteer, Testcontainers).
- `AUTOMATED-E2E` — full user-flow E2E.
- `BUILD-OUTPUT` — file/size/manifest assertion against a build artifact.
- `TYPECHECK` — `tsc --noEmit` or equivalent.
- `MANUAL` — human verification with documented residual risk.

If acceptance behavior depends on real layout APIs (`clientHeight`, `getBoundingClientRect`, `scrollTop`, `IntersectionObserver`, computed CSS), it must NOT be classified as `AUTOMATED-UNIT` in a jsdom environment. Promote to `AUTOMATED-INTEGRATION`, `AUTOMATED-E2E`, or `MANUAL` with documented residual risk.

## Status Discipline

A run artifact's `Status:` line uses one of: `Draft`, `Proposed`, or `Verified with evidence: <gate> @ <UTC> (exit=<code>)`. Self-assigned quality scores (`Quality target: 9/10`), bare `Ready for ...` stamps, and ✅ checkmarks on status lines are forbidden. Verification status is set only after a fresh gate run.

## Output

Use this shape for non-trivial work:

```md
# Plan: <short title>

**Status:** Draft

## Goal

## Run Artifact

## Affected Areas

## Owner

## Implementation Plan

## Acceptance Criteria

| ID | Criterion | Verification Method | Gate |
|---|---|---|---|

## Existing Behaviors Preserved

List each entry with an evidence-block citation and classify it as PRESERVED, INTENTIONALLY REMOVED, or BUG FIX.

## Verification

Gate command(s) and expected exit code. Status remains Draft/Proposed until a fresh gate run produces evidence.

## Required Gates

## Docs/Tests/Contracts To Update

## Risks

Use `- Risk: <risk>. Mitigation: <mitigation>.` for each non-empty bullet.
```

The `Implementation Plan`, `Acceptance Criteria`, `Existing Behaviors Preserved`, and `Verification` sections are required by the validator (`scripts/agent-validate-plan.sh`). Omitting any of them is a P0 plan defect.

## Limits

- Do not make broad edits while planning.
- Do not assign work across ownership boundaries without stating coordination.
- Do not weaken `rulebase.md`; propose explicit changes instead.
