---
description: Review a diff, plan, or code area using the repository review workflow.
argument-hint: [diff, path, PR, or review focus]
---

# Review

Read `.agent/rulebase.md`, `.agent/project-profile.md`, `.agent/ownership.md`, `.agent/gates.md`, `.agent/decisions.md`, and `.agent/workflows/review-workflow.md`.

If the invocation included arguments, for example after `/agent-bootstrap:review <focus>` or `agent:review <focus>`, treat them as the review scope.

Follow `.agent/workflows/review-workflow.md`:

1. Identify changed files, ownership areas, and relevant public contracts.
2. Review correctness, safety, contracts, data, security, performance, and tests.
3. Lead with actionable findings ordered by severity.
4. Include file and line references when available.
5. State verification gaps and residual risk.

Do not edit code during review unless the user explicitly asks for fixes after the review.
