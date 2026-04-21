# Rulebase

This file is the highest-priority project-specific rule source for agents.

## Objectives

Agents should optimize for:

1. Correctness of user-visible behavior.
2. Preservation of public contracts.
3. Small, reviewable diffs.
4. Alignment with existing architecture and conventions.
5. Verification through the narrowest sufficient gate.

## Always Required

- Re-read this file at the start of any coding task, even if it was read earlier in the session.
- Read `project-profile.md`, `ownership.md`, `gates.md`, and the relevant workflow before editing.
- Inspect existing patterns before introducing new abstractions.
- Keep changes scoped to the task and touched subsystem.
- Preserve user or teammate changes in the working tree.
- Update tests when behavior changes.
- Update docs when API, schema, CLI, workflow, or user-visible behavior changes.
- Report any gate that could not be run and why.

## Discipline Gates

These rules are hard gates for agent behavior, not style preferences.

```text
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION
NO PUBLIC CONTRACT CHANGE WITHOUT TESTS, DOCS, AND CONSUMER IMPACT CHECK
NO INVENTED COMMANDS, FILES, FUNCTIONS, GATES, OR REPO FACTS
NO UNRELATED CHANGES BUNDLED INTO THE TASK
```

If a rule cannot be satisfied, stop and report the blocker, the evidence gathered, and the remaining risk.

## Red Flags

Stop and re-check this rulebase when any of these thoughts apply:

- "This is a tiny change, so I can skip the workflow."
- "The command probably exists because this stack usually has it."
- "The tests should pass from inspection."
- "I can fix the symptom first and find the cause later."
- "I will clean up nearby code while I am here."
- "The public contract change is obvious, so docs/tests can wait."
- "The previous run was close enough."
- "The user wants speed, so verification can be summarized without running it."

## Rationalization Checks

| Excuse | Reality |
|---|---|
| "I already know the repo rules." | Re-read the rulebase at the start of each coding task. Session memory drifts. |
| "This command is conventional." | Only use commands found in checked-in repo files or mark the gate `not configured`. |
| "Manual inspection proves it." | Inspection is not fresh verification when an automated gate exists. |
| "The bug is obvious." | A bugfix needs root cause, expected behavior, actual behavior, and a proving gate or test gap. |
| "This refactor is harmless." | Unrequested refactors create review risk and can mask task-caused regressions. |
| "Docs/tests can be updated later." | Public behavior changes require docs/tests/consumer impact checks in the same task. |
| "The agent before me said it passed." | Verify independently before claiming status. |

## Forbidden Without Explicit Human Approval

- Deploying to production or shared environments.
- Running remote database migrations.
- Deleting, rewriting, or squashing existing migrations.
- Editing secrets, credentials, tokens, private keys, or `.env` values.
- Running destructive filesystem, database, or infrastructure commands.
- Bypassing authentication, authorization, validation, rate limiting, or audit logging to make a test pass.
- Weakening security headers, cookie protections, CSRF protections, encryption, or permission checks without an approved security decision.
- Changing public API, schema, package exports, or persisted data format without updating docs, tests, and all known consumers.

## Scope Control

- Prefer the narrowest role and ownership boundary capable of solving the task.
- Do not perform unrelated refactors while implementing a feature or bugfix.
- Do not rename public files, routes, commands, or exports unless the task explicitly requires it.
- Do not introduce a new framework, service, dependency, or runtime unless the existing stack cannot solve the problem cleanly.

## Correctness Rules

- Treat a patch as a candidate until the relevant gate passes.
- Use fresh command output before claiming that code is complete, fixed, passing, or ready.
- If a gate fails, inspect whether the failure is caused by the patch before making changes.
- Do not claim success from manual inspection alone when an automated gate exists.
- If no automated test exists for changed behavior, add one when practical or record the test gap.

## Contract Rules

When changing API behavior:

- Update API docs.
- Update shared types or client code.
- Add or update contract tests if configured.
- Preserve backwards compatibility unless explicitly approved.

When changing database behavior:

- Add forward migrations only.
- Preserve existing data.
- Include rollback guidance if the migration system supports it.
- Never run remote migrations without approval.

When changing UI behavior:

- Check responsive layout.
- Preserve accessibility basics: labels, keyboard flow, focus states, contrast.
- Avoid adding explanatory UI text that substitutes for clear interaction design.

## Rule Evolution Protocol

Agents may propose changes to this rulebase when a rule is incomplete, ambiguous, or repeatedly blocks beneficial work.

Rule changes must:

- Be explicit in the diff.
- Explain the trigger or incident.
- Preserve global safety constraints.
- Be reviewed like code.

Agents must not silently weaken rules involving security, secrets, production deploys, data deletion, remote migrations, or public contracts.

## Lessons Integration

If a mistake, incident, or repeated review finding reveals a durable rule, add a concise entry to `lessons.md`. Do not use `lessons.md` for transient task notes.
