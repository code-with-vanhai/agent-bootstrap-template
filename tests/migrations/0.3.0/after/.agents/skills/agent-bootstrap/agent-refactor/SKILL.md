---
name: agent-refactor
description: Use when the user invokes Agent Bootstrap command agent-refactor, agent:refactor, or asks Codex to run the refactor agent workflow.
---

# Agent Bootstrap refactor Command

This is a Codex wrapper skill for the canonical command file.

1. Read `.agent/commands/refactor.md`.
2. Treat the user's current request, including any text after `agent-refactor` or `agent:refactor`, as the command arguments or task context.
3. Follow `.agent/commands/refactor.md` exactly.
4. Keep `.agent/commands/refactor.md` as the source of truth; do not edit this wrapper when changing command behavior.
