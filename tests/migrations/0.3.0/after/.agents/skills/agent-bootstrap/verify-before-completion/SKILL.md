---
name: verify-before-completion
description: Use when about to report work complete, fixed, passing, ready, merged, reviewed, or safe after any coding, config, docs, gate, or agent-system change.
---

# Verify Before Completion

Completion claims require fresh evidence from the current task state.

## Hard Gate

```text
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

Before claiming work is complete:

1. Re-read `.agent/rulebase.md` and `.agent/gates.md`.
2. Identify the narrowest gate that proves the claim.
3. Run `scripts/agent-eval.sh <gate>` or explain why the gate is blocked or not configured.
4. Report command, result, skipped checks, failure excerpt, and residual risk.

## Red Flags

- Saying "done", "fixed", "passing", or "ready" before running a fresh command.
- Relying on a previous run, another agent's report, or manual inspection.
- Reporting only the happy path while hiding skipped checks.
- Treating `not configured` as success instead of residual risk.

## Canonical Sources

- `.agent/gates.md`
- `.agent/roles/gate-runner.md`
- `scripts/agent-eval.sh`
