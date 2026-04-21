# Feature Workflow

Use this workflow for new user-visible or system behavior.

## Steps

1. Planner defines goal, affected areas, owner, acceptance criteria, and gates.
2. Implementer inspects existing patterns and nearby tests.
3. Implementer makes a scoped patch.
4. Implementer updates tests and docs for changed behavior.
5. Gate Runner runs the selected gate.
6. Reviewer checks the diff if the change affects public contracts, data, auth, infra, or broad UI flows.
7. Record durable lessons or decisions only when needed.

## Acceptance Criteria

- Feature behavior matches the request.
- Public contracts are preserved or updated intentionally.
- Docs and tests reflect the behavior.
- Relevant gates pass or residual risk is explicit.

## Escalate Before Editing When

- The feature requires new infrastructure, external services, or paid APIs.
- The feature changes authentication, authorization, billing, data retention, or privacy behavior.
- The feature needs a new architecture decision.

