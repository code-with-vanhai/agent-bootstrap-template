# Rulebase

## Objectives

Agents should optimize for correctness, small diffs, existing Node.js patterns, and verified behavior.

## Always Required

- Re-read this file at the start of any coding task, even if it was read earlier in the session.
- Read `.agent/project-profile.md`, `.agent/ownership.md`, and `.agent/gates.md` before editing.
- Use commands from `package.json` only when configuring gates.
- Update tests when behavior changes.
- Report gates that could not be run.

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

- Running `npm run deploy`.
- Editing secrets, credentials, tokens, private keys, or `.env` values.
- Adding production infrastructure.
- Bypassing auth, validation, or rate limiting if those systems are added.
- Changing public API behavior without updating docs and tests.

## Scope Control

- Keep changes inside `src/` for implementation work unless tests/docs/scripts are required.
- Do not add dependencies unless the existing stack cannot solve the task cleanly.
- Use fresh command output before claiming that code is complete, fixed, passing, or ready.

## Rule Evolution

Rule changes must be explicit, reviewed, and preserve deployment, data, and security safety boundaries.
