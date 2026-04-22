---
description: Check release readiness without deploying, tagging, or mutating production state.
argument-hint: [release branch or version]
---

# Release Check

Read `.agent/rulebase.md`, `.agent/project-profile.md`, `.agent/gates.md`, `.agent/decisions.md`, and `.agent/workflows/release-check-workflow.md`.

If the invocation included arguments, for example after `/agent-bootstrap:release-check <desc>` or `agent:release-check <desc>`, treat them as the release branch, version, or release context.

Follow `.agent/workflows/release-check-workflow.md`.

This command is report-only:

- Run configured release-readiness checks.
- Inspect local repo state.
- Report blockers, skipped checks, and residual risk.
- Do not deploy.
- Do not tag.
- Do not push.
- Do not run remote migrations.
