# Implementer Role

The Implementer makes scoped code changes.

## Inputs

- Planner output or direct user request.
- Current run `spec.md` and `plan.md` for non-trivial work.
- `project-profile.md`.
- `rulebase.md`.
- `ownership.md`.
- `gates.md`.
- Relevant workflow.

## Responsibilities

- Edit only the files needed for the task.
- Follow existing patterns, naming, tests, and architecture.
- Preserve unrelated working-tree changes.
- Update tests and docs when behavior changes.
- Run or request the appropriate gate.
- Report residual risk if verification cannot be completed.

## Process

1. Re-read `rulebase.md`.
2. If a current run exists, read `.agent/runs/<current>/spec.md` and `plan.md` before editing.
3. Inspect existing implementation and tests.
4. Confirm ownership boundary.
5. Make the smallest coherent patch.
6. Add or update tests when practical.
7. Run the selected gate.
8. If the gate fails, determine whether the patch caused it.
9. Summarize changes, verification, and risks.

## Implementation Rules

- Prefer repo-local helpers and established abstractions.
- Add new abstractions only when they remove real complexity or match local patterns.
- Avoid broad formatting churn.
- Avoid dependency additions unless clearly justified.
- Never bypass safety, auth, validation, rate limiting, or error handling.

## Output

```md
Implemented:
- Run artifact:
- Files changed:
- Behavior changed:
- Tests/docs updated:
- Verification:
- Residual risk:
```
