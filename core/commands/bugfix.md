---
description: Fix a defect using the root-cause-first bugfix workflow.
argument-hint: <bug description>
---

# Bugfix

Read `.agent/rulebase.md`, `.agent/project-profile.md`, `.agent/ownership.md`, `.agent/gates.md`, and `.agent/workflows/bugfix-workflow.md`.

Task: $ARGUMENTS

If invoked as `agent:bugfix <desc>` in a non-Claude harness, treat the text after `agent:bugfix` as the bug description.

Follow `.agent/workflows/bugfix-workflow.md`:

1. Reproduce or narrow the bug before changing code.
2. State expected vs actual behavior.
3. Identify the subsystem, owner, and root cause.
4. Make the smallest fix that addresses the cause.
5. Add or update a regression test when practical.
6. Run the narrowest configured gate that proves the fix.
7. Report root cause, changed files, verification evidence, skipped gates, and residual risk.

Do not mask symptoms by weakening validation, auth, error handling, or tests.
