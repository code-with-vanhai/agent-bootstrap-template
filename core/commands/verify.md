---
description: Run configured repository verification gates and report evidence.
argument-hint: [changed|fast|frontend|backend|shared|e2e|full|security|release]
---

# Verify

Read `.agent/rulebase.md`, `.agent/gates.md`, `.agent/roles/gate-runner.md`, and `scripts/agent-eval.sh`.

If the invocation included arguments, for example after `/agent-bootstrap:verify <mode>` or `agent:verify <mode>`, treat the first argument as the gate mode.

Gate mode convention:

- Valid modes are `changed`, `fast`, `frontend`, `backend`, `shared`, `e2e`, `full`, `security`, and `release`.
- If no mode is supplied, choose the smallest sufficient configured gate from `.agent/gates.md`.
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
