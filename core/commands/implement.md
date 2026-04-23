---
description: Implement an approved plan with scoped edits and verification.
argument-hint: <run id or task description>
---

# Implement

Read `.agent/rulebase.md`, `.agent/project-profile.md`, `.agent/ownership.md`, `.agent/gates.md`, `.agent/decisions.md`, and `.agent/workflows/feature-workflow.md`.

Task: $ARGUMENTS

If invoked as `agent:implement <desc>` in a non-Claude harness, treat the text after `agent:implement` as the run id, plan path, or task description.

Argument priority:

1. If the argument matches an existing `.agent/runs/<run>/plan.md`, treat it as a run id.
2. Else if it matches an existing plan file path, treat it as the approved plan path.
3. Else treat the full argument string as the task description.

Execute the implementation phase only:

1. Find the approved plan in `.agent/runs/<run>/plan.md`, the current conversation, or the explicit invocation.
2. If no plan exists and the work is non-trivial, switch to `/agent-bootstrap:plan` behavior and stop before code.
3. Inspect existing patterns and nearby tests before editing.
4. Make scoped changes inside the intended ownership boundary.
5. Update tests and docs when behavior changes.
6. Run the gate selected in the plan, unless touched files require a broader configured gate.
7. Report changed files, verification evidence, skipped gates, and residual risk.

Do not broaden implementation into unrelated cleanup.
