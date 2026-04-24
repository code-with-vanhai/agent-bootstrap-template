---
name: agent-release-check
description: Use when the user invokes Agent Bootstrap command agent-release-check, agent:release-check, or asks Codex to run the release-check agent workflow.
---

# Agent Bootstrap release-check Command

This is a Codex wrapper skill for the canonical command file.

1. Read `.agent/commands/release-check.md`.
2. Treat the user's current request, including any text after `agent-release-check` or `agent:release-check`, as the command arguments or task context.
3. Follow `.agent/commands/release-check.md` exactly.
4. Keep `.agent/commands/release-check.md` as the source of truth; do not edit this wrapper when changing command behavior.
