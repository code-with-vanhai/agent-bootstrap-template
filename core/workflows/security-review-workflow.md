# Security Review Workflow

Use this workflow when a task touches authentication, authorization, secrets, permissions, user data, external integrations, deployment, migrations, cryptography, logging, or network boundaries.

Security review is separate from general code review because the failure mode is often silent and high impact.

## Steps

1. Identify the protected asset:
   - user data
   - credentials
   - session or token
   - permission boundary
   - payment or billing data
   - production infrastructure
   - private network or external service
2. Identify the trust boundary:
   - unauthenticated to authenticated
   - user to admin
   - client to server
   - server to third-party
   - local to remote environment
3. Check the changed code for:
   - auth bypass
   - missing authorization check
   - input validation gaps
   - output escaping or injection risk
   - unsafe deserialization
   - secret leakage in logs or errors
   - insecure cookie/session/token handling
   - missing rate limits or abuse controls
   - migration or data-retention risk
4. Confirm tests or gates cover the relevant behavior when configured.
5. Report findings before summaries.

When useful, tag findings with a recognized category such as OWASP Top 10 area or CWE identifier. Do not block a valid finding just because the exact category is unknown.

## Findings Format

```md
Findings:
- [severity] `file:line` - Security issue, exploit path, and recommended fix.

Assets affected:
- ...

Trust boundaries:
- ...

Verification gaps:
- ...
```

## Hard Rules

- Do not weaken auth, permissions, validation, rate limits, encryption, cookie protections, or logging safety to make a test pass.
- Do not expose secrets, tokens, or private keys in docs, tests, logs, screenshots, or examples.
- Do not run production deploys or remote migrations during review.
- If a security rule must change, use `rule-evolution-workflow.md` and require human review.
