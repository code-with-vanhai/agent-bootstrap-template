---
description: Review a diff, plan, or code area using the repository review workflow.
argument-hint: [diff, path, PR, or review focus]
allowed-tools: Read, Grep, Glob
---

# Review

Read `.agent/rulebase.md`, `.agent/project-profile.md`, `.agent/ownership.md`, `.agent/gates.md`, `.agent/decisions.md`, and `.agent/workflows/review-workflow.md`.

Task: $ARGUMENTS

If invoked as `agent:review <focus>` in a non-Claude harness, treat the text after `agent:review` as the review scope.

Follow `.agent/workflows/review-workflow.md`:

1. Identify changed files, ownership areas, and relevant public contracts.
2. Review correctness, safety, contracts, data, security, performance, and tests.
3. Lead with actionable findings ordered by severity.
4. Include file and line references when available.
5. State verification gaps and residual risk.

Do not edit code during review unless the user explicitly asks for fixes after the review.

## Plan/Spec Review

When the review target is `.agent/runs/*/plan.md` or `spec.md`:

1. **Grounding pass first.** For every evidence block, re-read the cited file at the current working tree and verify the snippet matches exactly (whitespace-normalized). Mismatch = P0 grounding defect.
2. **Behavior preservation pass.** For each modified function listed in `Existing Behaviors Preserved`, cross-check the claimed current side effects against actual source. Missing or wrong behaviors = P1 defect.
3. **Correctness pass.** Only after grounding and behavior passes are clean, evaluate the proposed AFTER for correctness, contracts, and risk.
4. **Loop control.** If grounding defects send the plan back to the planner more than 3 rounds, escalate to a human reviewer instead of iterating.

Do not iterate on solution quality while grounding is broken — return the plan to the planner for grounding revision.

If `scripts/agent-validate-plan.sh` is available, run it first and treat its `High` findings as P0 / P1 defects mechanically before applying judgement on the rest of the plan.
