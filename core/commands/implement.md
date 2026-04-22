---
description: Implement an approved plan with scoped edits and verification.
argument-hint: <run id or task description>
---

# Implement

Read `.agent/rulebase.md`, `.agent/project-profile.md`, `.agent/ownership.md`, `.agent/gates.md`, `.agent/decisions.md`, and `.agent/workflows/feature-workflow.md`.

If the invocation included arguments, for example after `/agent-bootstrap:implement <desc>` or `agent:implement <desc>`, treat them as the run id, plan path, or task description.

Execute the implementation phase only:

1. Find the approved plan in `.agent/runs/<run>/plan.md`, the current conversation, or the explicit invocation.
2. If no plan exists and the work is non-trivial, switch to `/agent-bootstrap:plan` behavior and stop before code.
3. Inspect existing patterns and nearby tests before editing.
4. Make scoped changes inside the intended ownership boundary.
5. Update tests and docs when behavior changes.
6. Run the gate selected in the plan, unless touched files require a broader configured gate.
7. Report changed files, verification evidence, skipped gates, and residual risk.

Do not broaden implementation into unrelated cleanup.
