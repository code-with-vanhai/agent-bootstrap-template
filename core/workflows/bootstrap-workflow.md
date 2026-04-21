# Bootstrap Workflow

Use this workflow when adding the agent system to an existing repository.

## Goal

Generate repo-specific `.agent/` instructions and thin tool adapters without changing business logic.

## Steps

1. Scan repository shape:
   - root files
   - package/build files
   - apps/packages/modules
   - docs
   - tests
   - CI workflows
   - deploy and migration scripts
2. Identify stack, ownership boundaries, public contracts, and dangerous operations.
3. Generate `.agent/` files from the template.
4. Generate `scripts/agent-eval.sh` from actual available commands.
5. Generate `scripts/agent-validate.sh` as the deterministic guardrail.
6. Add or update thin adapters for the tools used by the repo.
7. Run `bash scripts/agent-validate.sh`.
8. Report what was configured and what remains missing.

## Do Not

- Do not modify application code.
- Do not deploy.
- Do not run remote migrations.
- Do not edit secrets or env files.
- Do not invent tests or gates that do not exist.

## Output

```md
Bootstrap complete:
- Generated files:
- Detected stack:
- Configured gates:
- Not configured:
- Human follow-up:
```
