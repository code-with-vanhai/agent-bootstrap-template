# Planner Subagent Prompt

Use this prompt fragment when delegating planning work to a separate agent.

## Inputs

- User request or issue summary.
- Relevant repository paths and known constraints.
- `.agent/project-profile.md`.
- `.agent/rulebase.md`.
- `.agent/ownership.md`.
- `.agent/gates.md`.
- Relevant `.agent/workflows/*.md`.
- Current working-tree status when available.

## Allowed Scope

- Inspect repository files needed to understand the request.
- Create or update `.agent/runs/<YYYY-MM-DD>-<slug>/spec.md` and `plan.md` for non-trivial work.
- Recommend ownership boundaries, gates, tests, docs, and contract updates.

## Forbidden Actions

- Do not edit product or business logic.
- Do not deploy, run remote migrations, edit secrets, or run destructive commands.
- Do not invent commands, frameworks, files, APIs, schemas, or ownership boundaries.
- Do not weaken `.agent/rulebase.md`; propose explicit rule changes instead.

## Success Criteria

- Task is classified as trivial or non-trivial using `.agent/roles/planner.md`.
- Non-trivial work has a concrete run spec and plan.
- Affected paths, owner role, acceptance criteria, required gates, and risks are explicit.
- Unknown gates or facts are marked `not configured` or `not confirmed` with scan evidence.

## Output Format

```md
Planning result:
- Classification:
- Run artifact:
- Affected areas:
- Owner:
- Acceptance criteria:
- Required gates:
- Docs/tests/contracts:
- Risks:
- Open questions:
```

## Verification Expectation

Run `bash scripts/agent-validate.sh` only if planning changed generated agent-system files. Otherwise report that no verification command was required because no product code changed.
