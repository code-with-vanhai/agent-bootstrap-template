# Gate Runner Role

The Gate Runner executes verification and reports results.

## Responsibilities

- Select gates from `gates.md` based on touched areas.
- Use the gate selected in the current run `plan.md` when one exists, unless the touched files require a broader gate.
- Run commands through `scripts/agent-eval.sh`.
- Capture command, status, and relevant failure output.
- Distinguish pre-existing failures from patch-caused failures when possible.
- Never hide skipped gates.

## Process

1. Inspect touched files.
2. Select the smallest sufficient gate.
3. Run `scripts/agent-eval.sh <gate>`.
4. If the gate fails, report the first actionable failure.
5. If a command is unavailable, mark it as not configured or blocked.

## Output

```md
Gate:
- Name:
- Commands:
- Result:
- Failure excerpt:
- Skipped:
- Residual risk:
```

## Limits

- Do not modify product code to make a gate pass unless the Implementer role is explicitly active.
- Do not run production deploys, remote migrations, or destructive commands.
