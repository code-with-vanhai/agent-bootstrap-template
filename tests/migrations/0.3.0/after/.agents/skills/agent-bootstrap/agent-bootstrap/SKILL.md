---
name: agent-bootstrap
description: Use when the user invokes Agent Bootstrap command agent-bootstrap, agent:bootstrap, or asks Codex to run the bootstrap agent workflow.
---

# Agent Bootstrap bootstrap Command

This is a Codex wrapper skill for the canonical command file.

1. Read `.agent/commands/bootstrap.md`.
2. Treat the user's current request, including any text after `agent-bootstrap` or `agent:bootstrap`, as the command arguments or task context.
3. Follow `.agent/commands/bootstrap.md` exactly.
4. Keep `.agent/commands/bootstrap.md` as the source of truth; do not edit this wrapper when changing command behavior.
