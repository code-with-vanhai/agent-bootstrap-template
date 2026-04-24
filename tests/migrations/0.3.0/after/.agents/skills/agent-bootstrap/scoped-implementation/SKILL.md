---
name: scoped-implementation
description: Use when editing code, tests, docs, config, generated agent files, or any repository artifact where unrelated changes are possible.
---

# Scoped Implementation

Small, reviewable diffs are a correctness tool.

## Hard Gate

```text
NO UNRELATED CHANGES BUNDLED INTO THE TASK
```

Before editing:

1. Re-read `.agent/rulebase.md` and `.agent/ownership.md`.
2. Identify the owner role and allowed paths.
3. State any cross-boundary coordination before touching files.
4. Keep formatting, renames, dependency changes, and refactors out unless the task requires them.

## Red Flags

- "While I am here..."
- "This nearby code could use cleanup."
- "I'll reformat this file for consistency."
- "This unrelated test is easy to fix too."
- "The task is small, so ownership does not matter."

## Canonical Sources

- `.agent/ownership.md`
- `.agent/roles/implementer.md`
- `.agent/rulebase.md`
