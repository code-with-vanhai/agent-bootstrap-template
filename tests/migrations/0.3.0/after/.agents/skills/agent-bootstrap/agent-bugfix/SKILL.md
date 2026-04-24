---
name: agent-bugfix
description: Use when the user invokes Agent Bootstrap command agent-bugfix, agent:bugfix, or asks Codex to run the bugfix agent workflow.
---

# Agent Bootstrap bugfix Command

This is a Codex wrapper skill for the canonical command file.

1. Read `.agent/commands/bugfix.md`.
2. Treat the user's current request, including any text after `agent-bugfix` or `agent:bugfix`, as the command arguments or task context.
3. Follow `.agent/commands/bugfix.md` exactly.
4. Keep `.agent/commands/bugfix.md` as the source of truth; do not edit this wrapper when changing command behavior.
