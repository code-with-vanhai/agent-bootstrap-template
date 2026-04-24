---
description: Check release readiness without deploying, tagging, or mutating production state.
argument-hint: [release branch or version]
---

# Release Check

Read `.agent/rulebase.md`, `.agent/project-profile.md`, `.agent/gates.md`, `.agent/decisions.md`, and `.agent/workflows/release-check-workflow.md`.

Task: $ARGUMENTS

If invoked as `agent:release-check <desc>` in a non-Claude harness, treat the text after `agent:release-check` as the release branch, version, or release context.

Follow `.agent/workflows/release-check-workflow.md`.

This command is report-only:

- Run configured release-readiness checks.
- Inspect local repo state.
- Report blockers, skipped checks, and residual risk.
- Do not deploy.
- Do not tag.
- Do not push.
- Do not run remote migrations.
