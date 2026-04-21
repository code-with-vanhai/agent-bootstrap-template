# Ownership

Ownership maps files and subsystems to the agent role that should lead changes.

## Path Ownership

| Path pattern | Owner role | Coordination required when |
|---|---|---|
| `{{FRONTEND_PATH_PATTERN}}` | `{{FRONTEND_ROLE_OR_IMPLEMENTER}}` | API contracts, shared types, auth, routing, e2e flows change |
| `{{BACKEND_PATH_PATTERN}}` | `{{BACKEND_ROLE_OR_IMPLEMENTER}}` | Public API, schema, auth, infra, queues, background jobs change |
| `{{SHARED_PATH_PATTERN}}` | `{{SHARED_CONTRACT_ROLE_OR_IMPLEMENTER}}` | Any consumer in another app/package is affected |
| `{{DOCS_PATH_PATTERN}}` | `{{REVIEWER_OR_IMPLEMENTER}}` | Docs describe public behavior, API, schema, or deployment |
| `{{TEST_PATH_PATTERN}}` | `{{REVIEWER_OR_IMPLEMENTER}}` | Tests encode cross-subsystem behavior |

## Role Ownership

| Role | Primary responsibility | Must not do alone |
|---|---|---|
| Planner | Task decomposition and subsystem selection | Make broad code edits without assigning ownership |
| Implementer | Scoped code changes | Change public contracts without docs/tests and coordination |
| Reviewer | Risk review and quality assessment | Rewrite implementation unless asked |
| Gate Runner | Verification execution and reporting | Modify code to force gates green without owner context |

## Cross-Boundary Protocol

If a change touches multiple ownership areas:

1. State the affected areas.
2. Identify the lead owner.
3. List required docs/tests/contracts to update.
4. Run the highest relevant combined gate.

## Conflict Protocol

If the working tree contains unrelated changes:

- Do not revert them.
- Work around them when possible.
- If they block the task, report the conflict and ask for direction.

## High-Risk Areas

Paths that require extra caution:

- `{{HIGH_RISK_PATH_1_OR_NONE}}`
- `{{HIGH_RISK_PATH_2_OR_NONE}}`

