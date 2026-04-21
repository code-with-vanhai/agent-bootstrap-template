# Project Profile

Generated from repo scan on: `2026-04-21T00:00:00Z`

## Purpose

Small Node.js API sample used to demonstrate a completed agent bootstrap instantiation.

## Stack

| Area | Value |
|---|---|
| Primary language | `TypeScript` |
| Runtime | `Node.js` |
| Frontend | `not applicable` |
| Backend | `Node.js API` |
| Database | `not configured` |
| Infrastructure | `not confirmed` |
| Package manager | `npm` |
| Test frameworks | `Vitest` |
| Deployment target | `not confirmed` |

## Repository Map

| Path | Purpose | Notes |
|---|---|---|
| `src/` | Application source | Backend/API code if present |
| `tests/` | Unit or integration tests | Not present in this minimal sample |
| `scripts/` | Repository scripts | Contains agent gate runner |
| `.agent/` | Canonical agent instructions | Shared by all tools |

## Critical Docs

- `README.md`: sample purpose and usage notes.
- `.agent/gates.md`: verification commands and not-configured gates.

## Public Surface

- API routes: expected under `src/routes/` if implemented.
- Package exports: none found in `package.json`.
- CLI commands: npm scripts in `package.json`.
- Config format: none found.

## Dangerous Operations

The following operations require explicit human approval:

- `npm run deploy`: deploy placeholder found in `package.json`.
- Remote migrations: none found.
- Data deletion scripts: none found.
- Secret locations: none found.

## Verification Summary

Use `scripts/agent-eval.sh`.

| Gate | Status | Command |
|---|---|---|
| `fast` | `configured` | `scripts/agent-eval.sh fast` |
| `backend` | `configured` | `scripts/agent-eval.sh backend` |
| `full` | `configured` | `scripts/agent-eval.sh full` |
| `frontend` | `not configured` | no frontend framework found |
| `e2e` | `not configured` | no e2e framework found |

## Current Gaps

- No real source files in this sample.
- No CI workflow in this sample.
- No e2e tests configured.

