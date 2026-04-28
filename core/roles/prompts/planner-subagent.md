# Planner Subagent Prompt

Use this prompt fragment when delegating planning work to a separate agent.

## Inputs

- User request or issue summary.
- Relevant repository paths and known constraints.
- `.agent/project-profile.md`.
- `.agent/rulebase.md`.
- `.agent/ownership.md`.
- `.agent/gates.md`.
- Relevant `.agent/workflows/*.md`.
- Current working-tree status when available.

## Allowed Scope

- Inspect repository files needed to understand the request.
- Create or update `.agent/runs/<YYYY-MM-DD>-<slug>/spec.md` and `plan.md` for non-trivial work.
- Recommend ownership boundaries, gates, tests, docs, and contract updates.

## Forbidden Actions

- Do not edit product or business logic.
- Do not deploy, run remote migrations, edit secrets, or run destructive commands.
- Do not invent commands, frameworks, files, APIs, schemas, or ownership boundaries.
- Do not weaken `.agent/rulebase.md`; propose explicit rule changes instead.
- Do not fabricate "BEFORE" / "Existing" code snippets. Re-read the cited file in the same planning turn before quoting.
- Do not self-assign quality scores, ✅ checkmarks, or `Ready for ...` stamps. Status is `Draft`, `Proposed`, or `Verified with evidence: <gate> @ <UTC> (exit=<code>)` only.

## Required Plan Sections

For non-trivial work, the produced `plan.md` must contain:

- `Implementation Plan` — concrete implementation steps. Do not leave behavior-affecting choices as `consider`, `maybe`, `could`, `or add`, or similar hedges; resolve the choice or move it to `Open Questions`.
- `Acceptance Criteria` — every row classified with a Verification Method (`AUTOMATED-UNIT`, `AUTOMATED-INTEGRATION`, `AUTOMATED-E2E`, `BUILD-OUTPUT`, `TYPECHECK`, or `MANUAL`). Layout-dependent behavior cannot be `AUTOMATED-UNIT` in jsdom.
- `Existing Behaviors Preserved` — for each modified function, current side effects with evidence-block citations and classification (`PRESERVED`, `INTENTIONALLY REMOVED`, `BUG FIX`).
- `Verification` — gate name and command(s).

`Open Questions` is optional. If present, each `- Q:` bullet must have a following `- RESOLVED:` or `- DEFERRED:` bullet. For `Status: Proposed`, unresolved questions are plan defects.

When adding enum/status/error-code/message literals, include a `Contract Value Table` section and cite existing naming conventions with an evidence block. For cross-boundary changes, include a `Compatibility Matrix` section. When adding/updating/keeping tests, include a `Test Delta` section. Non-empty `Risks` bullets must include `Mitigation:`.

## Evidence Block Format

Every "BEFORE" / "Existing" / "Current code" quote uses this format. The grammar is canonical in `.agent/workflows/feature-workflow.md`.

````md
<!-- current-code path=<repo-relative-posix> lines=A-B ref=<short-sha> region_sha256=<full-hex> -->
```<lang>
<exact snippet>
```
<!-- /current-code -->
````

Re-read the cited file before writing the block. If the snippet you expected is not present at the cited region, stop and revise the plan goal — do not fabricate a snippet that fits the proposed AFTER.

## Success Criteria

- Task is classified as trivial or non-trivial using `.agent/roles/planner.md`.
- Non-trivial work has a concrete run spec and plan.
- Affected paths, owner role, acceptance criteria, required gates, and risks are explicit.
- Unknown gates or facts are marked `not configured` or `not confirmed` with scan evidence.

## Output Format

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

## Verification

## Required Gates

## Docs/Tests/Contracts To Update

## Risks
```

## Verification Expectation

Run `bash scripts/agent-validate.sh` only if planning changed generated agent-system files. Otherwise report that no verification command was required because no product code changed.
