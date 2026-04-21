# Refactor Workflow

Use this workflow when changing internal structure without intended behavior change.

## Steps

1. Define the refactor goal and non-goals.
2. Identify behavior that must remain unchanged.
3. Inspect tests or add characterization tests when risk is high.
4. Make incremental changes.
5. Run gates that prove behavior is preserved.
6. Update docs only if architecture or development workflow changes.

## Acceptance Criteria

- No intended public behavior change.
- Diff improves maintainability, removes meaningful duplication, or aligns with established architecture.
- Relevant tests and build gates pass.

## Escalate Before Editing When

- The refactor crosses ownership boundaries.
- Public contracts, storage formats, migrations, or deploy topology may change.
- Existing tests are too weak to prove behavior preservation.

