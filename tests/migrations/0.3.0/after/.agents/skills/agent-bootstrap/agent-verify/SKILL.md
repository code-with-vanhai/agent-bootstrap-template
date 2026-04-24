---
name: agent-verify
description: Use when the user invokes Agent Bootstrap command agent-verify, agent:verify, or asks Codex to run the verify agent workflow.
---

# Agent Bootstrap verify Command

This is a Codex wrapper skill for the canonical command file.

1. Read `.agent/commands/verify.md`.
2. Treat the user's current request, including any text after `agent-verify` or `agent:verify`, as the command arguments or task context.
3. Follow `.agent/commands/verify.md` exactly.
4. Keep `.agent/commands/verify.md` as the source of truth; do not edit this wrapper when changing command behavior.
