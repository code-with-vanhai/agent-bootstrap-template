# Project Profile

Generated from repo scan on: `{{INSTANTIATED_AT_ISO8601}}`

## Purpose

{{ONE_PARAGRAPH_DESCRIPTION_OF_THE_PRODUCT_OR_LIBRARY}}

## Stack

| Area | Value |
|---|---|
| Primary language | `{{PRIMARY_LANGUAGE}}` |
| Runtime | `{{RUNTIME}}` |
| Frontend | `{{FRONTEND_STACK_OR_NOT_APPLICABLE}}` |
| Backend | `{{BACKEND_STACK_OR_NOT_APPLICABLE}}` |
| Database | `{{DATABASE_OR_NOT_APPLICABLE}}` |
| Infrastructure | `{{INFRA_OR_NOT_APPLICABLE}}` |
| Package manager | `{{PACKAGE_MANAGER_OR_NOT_APPLICABLE}}` |
| Test frameworks | `{{TEST_FRAMEWORKS_OR_NOT_CONFIGURED}}` |
| Deployment target | `{{DEPLOYMENT_TARGET_OR_NOT_CONFIGURED}}` |

## Repository Map

| Path | Purpose | Notes |
|---|---|---|
| `{{PATH_1}}` | {{PURPOSE_1}} | {{NOTES_1}} |
| `{{PATH_2}}` | {{PURPOSE_2}} | {{NOTES_2}} |

## Critical Docs

- `{{DOC_PATH_1}}`: {{WHY_IT_MATTERS}}
- `{{DOC_PATH_2}}`: {{WHY_IT_MATTERS}}

## Public Contracts

List contracts that must not change casually:

- API response/request shapes: `{{API_CONTRACT_PATH_OR_NOT_FOUND}}`
- Database schema and migrations: `{{SCHEMA_PATH_OR_NOT_FOUND}}`
- CLI commands: `{{CLI_DOC_PATH_OR_NOT_APPLICABLE}}`
- Package exports: `{{EXPORTS_PATH_OR_NOT_APPLICABLE}}`
- UI routes or deep links: `{{ROUTES_DOC_OR_NOT_APPLICABLE}}`

## Dangerous Operations

The following operations require explicit human approval:

- Production deploys: `{{DEPLOY_COMMANDS_OR_NOT_CONFIGURED}}`
- Remote migrations: `{{REMOTE_MIGRATION_COMMANDS_OR_NOT_CONFIGURED}}`
- Data deletion or destructive scripts: `{{DESTRUCTIVE_COMMANDS_OR_NOT_FOUND}}`
- Secret/key rotation: `{{SECRET_LOCATIONS_OR_NOT_FOUND}}`

## Verification Summary

Use `scripts/agent-eval.sh`.

| Gate | Status | Command |
|---|---|---|
| `fast` | `{{CONFIGURED_OR_NOT_CONFIGURED}}` | `scripts/agent-eval.sh fast` |
| `changed` | `{{CONFIGURED_OR_NOT_CONFIGURED}}` | `scripts/agent-eval.sh changed` |
| `full` | `{{CONFIGURED_OR_NOT_CONFIGURED}}` | `scripts/agent-eval.sh full` |

## Current Gaps

Record missing safety or quality infrastructure honestly:

- {{GAP_1_OR_NONE}}
- {{GAP_2_OR_NONE}}

## Agent Notes

- Prefer existing local patterns before adding abstractions.
- If behavior changes, update tests and relevant docs.
- If a task crosses ownership boundaries, state the coordination plan before editing.
