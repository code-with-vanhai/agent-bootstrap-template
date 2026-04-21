# Rulebase

## Objectives

Agents should optimize for correctness, small diffs, existing Node.js patterns, and verified behavior.

## Always Required

- Read `.agent/project-profile.md`, `.agent/ownership.md`, and `.agent/gates.md` before editing.
- Use commands from `package.json` only when configuring gates.
- Update tests when behavior changes.
- Report gates that could not be run.

## Forbidden Without Explicit Human Approval

- Running `npm run deploy`.
- Editing secrets, credentials, tokens, private keys, or `.env` values.
- Adding production infrastructure.
- Bypassing auth, validation, or rate limiting if those systems are added.
- Changing public API behavior without updating docs and tests.

## Scope Control

- Keep changes inside `src/` for implementation work unless tests/docs/scripts are required.
- Do not add dependencies unless the existing stack cannot solve the task cleanly.

## Rule Evolution

Rule changes must be explicit, reviewed, and preserve deployment, data, and security safety boundaries.

