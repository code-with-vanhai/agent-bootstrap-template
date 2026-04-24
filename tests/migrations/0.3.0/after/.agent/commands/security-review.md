---
description: Review security-sensitive changes, assets, and trust boundaries.
argument-hint: [diff, path, PR, or security focus]
allowed-tools: Read, Grep, Glob
---

# Security Review

Read `.agent/rulebase.md`, `.agent/project-profile.md`, `.agent/ownership.md`, `.agent/gates.md`, `.agent/decisions.md`, and `.agent/workflows/security-review-workflow.md`.

Task: $ARGUMENTS

If invoked as `agent:security-review <focus>` in a non-Claude harness, treat the text after `agent:security-review` as the security review scope.

Follow `.agent/workflows/security-review-workflow.md`:

1. Identify protected assets and trust boundaries.
2. Check auth, authorization, input validation, output escaping, deserialization, secrets, token/session handling, rate limits, migration risk, data retention, logging, and external integrations.
3. Confirm tests or configured gates cover the relevant behavior when available.
4. Lead with actionable findings ordered by severity.
5. Include file and line references when available.
6. State verification gaps and residual risk.

Do not edit code during security review unless the user explicitly asks for fixes after the review.
