# Constitution

Non-negotiable safety and discipline constraints for agents working in this repository.

This file is **not** updated through the rule-evolution workflow. Changes require explicit human approval and should be reviewed like a security-impacting policy change.

## Discipline Gates

These rules are hard gates for agent behavior, not style preferences.

```text
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION
NO PUBLIC CONTRACT CHANGE WITHOUT TESTS, DOCS, AND CONSUMER IMPACT CHECK
NO INVENTED COMMANDS, FILES, FUNCTIONS, GATES, OR REPO FACTS
NO UNRELATED CHANGES BUNDLED INTO THE TASK
```

If a rule cannot be satisfied, stop and report the blocker, the evidence gathered, and the remaining risk.

## Forbidden Without Explicit Human Approval

- Deploying to production or shared environments.
- Running remote database migrations.
- Deleting, rewriting, or squashing existing migrations.
- Editing secrets, credentials, tokens, private keys, or `.env` values.
- Running destructive filesystem, database, or infrastructure commands.
- Bypassing authentication, authorization, validation, rate limiting, or audit logging to make a test pass.
- Weakening security headers, cookie protections, CSRF protections, encryption, or permission checks without an approved security decision.
- Changing public API, schema, package exports, or persisted data format without updating docs, tests, and all known consumers.

## Database & Migration Invariants

- Add forward migrations only.
- Preserve existing data.
- Include rollback guidance if the migration system supports it.
- Never run remote migrations without approval.

## Amendment

Amendments require explicit human approval. They do not flow through the rule-evolution workflow. Treat security-impacting amendments with the same scrutiny as a production policy change.
