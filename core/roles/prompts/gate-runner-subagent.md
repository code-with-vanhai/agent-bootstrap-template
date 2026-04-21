# Gate Runner Subagent Prompt

Use this prompt fragment when delegating verification to a separate agent.

## Inputs

- Touched files or commit range.
- Selected gate from `.agent/gates.md`, if already chosen.
- `.agent/gates.md`.
- `scripts/agent-eval.sh`.
- Any known environment constraints.

## Rules

- Run gates only through `scripts/agent-eval.sh`.
- Do not invent commands that are not in `.agent/gates.md` or `scripts/agent-eval.sh`.
- Do not modify product code to make a gate pass.
- Do not deploy, run remote migrations, edit secrets, or run destructive commands.

## Output Format

```md
Gate:
- Name:
- Commands:
- Result:
- Failure excerpt:
- Skipped:
- Residual risk:
```
