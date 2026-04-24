---
description: Run configured repository verification gates and report evidence.
argument-hint: [changed|fast|frontend|backend|shared|e2e|full|security|release]
---

# Verify

Read `.agent/rulebase.md`, `.agent/gates.md`, `.agent/roles/gate-runner.md`, and `scripts/agent-eval.sh`.

Task: $ARGUMENTS

If invoked as `agent:verify <mode>` in a non-Claude harness, treat the text after `agent:verify` as the gate mode.

Gate mode convention:

- This command accepts zero or one argument.
- Valid modes are `changed`, `fast`, `frontend`, `backend`, `shared`, `e2e`, `full`, `security`, and `release`.
- If no mode is supplied, choose the smallest sufficient configured gate from `.agent/gates.md`.
- If more than one argument token is supplied, report the invocation as unsupported and do not run a gate.
- Map the mode directly to `scripts/agent-eval.sh <mode>`.
- If the requested mode is not configured, report it as `not configured`; do not invent a substitute command.

Run the selected gate and report:

- Gate name.
- Commands run.
- Pass/fail status.
- Relevant failure excerpts.
- Skipped checks and reasons.
- Residual risk.

Do not deploy, tag, run remote migrations, or run destructive commands.
