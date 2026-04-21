---
name: plan-before-code
description: Use when implementing non-trivial work, cross-subsystem changes, risky refactors, public contract changes, or tasks where acceptance criteria are unclear.
---

# Plan Before Code

Non-trivial work needs an explicit spec and plan before implementation.

## Hard Gate

```text
NO NON-TRIVIAL IMPLEMENTATION WITHOUT A RUN SPEC AND PLAN
```

Inline planning is allowed only when all are true:

- At most 2 files are expected to change.
- Expected diff is at most 30 lines.
- No public API, schema, export, persisted format, auth, security, deploy, or migration behavior changes.
- No new dependency, runtime, infrastructure, or cross-subsystem ownership change is needed.

When in doubt, write the plan. When heuristic and engineering judgment disagree, engineering judgment wins.

## Run Artifacts

```text
.agent/runs/<YYYY-MM-DD>-<slug>/spec.md
.agent/runs/<YYYY-MM-DD>-<slug>/plan.md
```

## Canonical Sources

- `.agent/roles/planner.md`
- `.agent/runs/`
- `.agent/workflows/`
