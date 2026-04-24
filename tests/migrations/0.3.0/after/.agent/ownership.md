# Ownership

Ownership maps files and subsystems to the agent role that should lead changes.

## Path Ownership

| Path pattern | Owner role | Coordination required when |
|---|---|---|
| `not confirmed` | `not confirmed` | API contracts, shared types, auth, routing, e2e flows change |
| `not confirmed` | `not confirmed` | Public API, schema, auth, infra, queues, background jobs change |
| `not confirmed` | `not confirmed` | Any consumer in another app/package is affected |
| `not confirmed` | `not confirmed` | Docs describe public behavior, API, schema, or deployment |
| `not confirmed` | `not confirmed` | Tests encode cross-subsystem behavior |

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

- `not confirmed`
- `not confirmed`

