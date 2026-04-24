---
description: Refactor internal structure while preserving observable behavior.
argument-hint: <refactor goal or scope>
---

# Refactor

Read `.agent/rulebase.md`, `.agent/project-profile.md`, `.agent/ownership.md`, `.agent/gates.md`, `.agent/decisions.md`, and `.agent/workflows/refactor-workflow.md`.

Task: $ARGUMENTS

If invoked as `agent:refactor <desc>` in a non-Claude harness, treat the text after `agent:refactor` as the refactor goal or scope.

Follow `.agent/workflows/refactor-workflow.md`:

1. Define the refactor goal and non-goals.
2. Identify behavior that must remain unchanged.
3. Inspect tests or add characterization tests when risk is high.
4. Make incremental changes inside the intended ownership boundary.
5. Run gates that prove behavior is preserved.
6. Report changed files, behavior-preservation evidence, skipped gates, and residual risk.

Do not change public behavior, public contracts, storage formats, migrations, deploy topology, auth, or security behavior unless the user explicitly changes the task from refactor to implementation.
