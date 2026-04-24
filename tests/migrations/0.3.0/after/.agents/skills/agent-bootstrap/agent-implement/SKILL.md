---
name: agent-implement
description: Use when the user invokes Agent Bootstrap command agent-implement, agent:implement, or asks Codex to run the implement agent workflow.
---

# Agent Bootstrap implement Command

This is a Codex wrapper skill for the canonical command file.

1. Read `.agent/commands/implement.md`.
2. Treat the user's current request, including any text after `agent-implement` or `agent:implement`, as the command arguments or task context.
3. Follow `.agent/commands/implement.md` exactly.
4. Keep `.agent/commands/implement.md` as the source of truth; do not edit this wrapper when changing command behavior.
