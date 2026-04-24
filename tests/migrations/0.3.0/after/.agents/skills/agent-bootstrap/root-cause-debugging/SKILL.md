---
name: root-cause-debugging
description: Use when investigating bugs, failed tests, regressions, incidents, unexpected behavior, flaky results, or repeated failed fixes.
---

# Root Cause Debugging

Bugfixes must explain the cause, not just change the symptom.

## Hard Gate

```text
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION
```

Before editing:

1. Reproduce or narrow the failure.
2. Identify expected vs actual behavior.
3. Check recent changes and relevant ownership boundaries.
4. State the root cause or the evidence still missing.
5. Add or update a regression test when practical.

## Red Flags

- "The fix is obvious."
- "Try this quick patch first."
- "The test is probably wrong."
- "We can clean up the code while debugging."
- "It only failed once, so no root cause is needed."

## Canonical Sources

- `.agent/workflows/bugfix-workflow.md`
- `.agent/rulebase.md`
- `.agent/lessons.md`
