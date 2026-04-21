# Review Workflow

Use this workflow for code review, architecture review, rulebase review, or risky diffs.

## Steps

1. Identify changed files and ownership areas.
2. Read relevant `.agent/` files and decisions.
3. Review correctness, safety, contracts, data, security, performance, and tests.
4. Lead with actionable findings ordered by severity.
5. State verification gaps and residual risk.

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

