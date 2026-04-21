# Implementer Subagent Prompt

Use this prompt fragment when delegating scoped implementation work to a separate agent.

## Inputs

- User request or assigned task.
- Current run `.agent/runs/<YYYY-MM-DD>-<slug>/spec.md` and `plan.md` for non-trivial work.
- `.agent/project-profile.md`.
- `.agent/rulebase.md`.
- `.agent/ownership.md`.
- `.agent/gates.md`.
- Relevant workflow and role files.
- Allowed paths and forbidden paths.

## Allowed Scope

- Edit only files needed for the assigned task.
- Add or update tests and docs required by the behavior change.
- Run the narrowest sufficient gate through `scripts/agent-eval.sh`.

## Forbidden Actions

- Do not change files outside the assigned ownership boundary without reporting the need for coordination.
- Do not perform unrelated refactors, formatting churn, or cleanup.
- Do not deploy, run remote migrations, edit secrets, or run destructive commands.
- Do not bypass auth, validation, rate limiting, security checks, or tests to make a gate pass.
- Do not invent commands, files, APIs, schemas, or test results.

## Success Criteria

- Implementation matches the current spec and plan.
- Diff is small, scoped, and follows existing repo patterns.
- Public contracts, docs, and tests are updated when behavior changes.
- Relevant gate is run, or blocked/not-configured status is reported with residual risk.

## Output Format

```md
Implemented:
- Run artifact:
- Files changed:
- Behavior changed:
- Tests/docs/contracts updated:
- Verification:
- Residual risk:
```

## Verification Expectation

Before claiming completion, run the selected gate from `.agent/gates.md` or explain why it is blocked or not configured. Include the exact command and result.
