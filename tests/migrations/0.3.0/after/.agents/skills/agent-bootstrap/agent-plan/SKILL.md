---
name: agent-plan
description: Use when the user invokes Agent Bootstrap command agent-plan, agent:plan, or asks Codex to run the plan agent workflow.
---

# Agent Bootstrap plan Command

This is a Codex wrapper skill for the canonical command file.

1. Read `.agent/commands/plan.md`.
2. Treat the user's current request, including any text after `agent-plan` or `agent:plan`, as the command arguments or task context.
3. Follow `.agent/commands/plan.md` exactly.
4. Keep `.agent/commands/plan.md` as the source of truth; do not edit this wrapper when changing command behavior.
