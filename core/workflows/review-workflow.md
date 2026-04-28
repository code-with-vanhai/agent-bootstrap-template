# Review Workflow

Use this workflow for code review, architecture review, rulebase review, or risky diffs.

## Steps

1. Identify changed files and ownership areas.
2. Read relevant `.agent/` files and decisions.
3. Review correctness, safety, contracts, data, security, performance, and tests.
4. Lead with actionable findings ordered by severity.
5. State verification gaps and residual risk.

## Plan/Spec Review

When the review target is `.agent/runs/*/plan.md` or `spec.md`, apply these passes in order. Do not skip ahead while an earlier pass is failing.

1. **Grounding pass first.** For every evidence block in the plan, re-read the cited file at the current working tree and verify the snippet matches exactly (whitespace-normalized). Mismatch is a P0 grounding defect; return the plan to the planner.
2. **Behavior preservation pass.** Cross-check each `Existing Behaviors Preserved` entry against actual source. Missing or wrong behaviors are P1 defects.
3. **Correctness pass.** Only after the first two passes are clean, evaluate the proposed AFTER for correctness, contracts, and risk.
4. **Loop control.** If grounding defects send the plan back to the planner more than 3 rounds, escalate to a human reviewer instead of iterating.

Do not iterate on solution quality while grounding is broken.

If `scripts/agent-validate-plan.sh` is available, run it first; treat its `High` findings as P0 / P1 mechanically before applying judgement on the rest of the plan.

During the correctness pass, check the `Decision Ledger` when the plan contains fallback/empty/null/degraded behavior, thresholds/timeouts/debounce/limits, matchers/classifiers/parsers/blocklists/allowlists, or test-harness choices. If the plan leaves caller/user impact, threshold rationale, algorithm choice, or mock/fake-timer setup implicit, return it to the planner even if the mechanical validator is otherwise clean.

## Severity Guidance

- Critical: data loss, security bypass, production outage, broken deploy, irreversible migration.
- High: public contract break, auth/permission flaw, major user-flow regression, untested risky behavior.
- Medium: likely edge-case bug, missing important test, performance issue, maintainability risk.
- Low: minor maintainability issue with clear impact.

## Output

```md
Findings:
- [severity] `file:line` - Problem, impact, and suggested direction.

Open questions:
- ...

Verification gaps:
- ...
```
