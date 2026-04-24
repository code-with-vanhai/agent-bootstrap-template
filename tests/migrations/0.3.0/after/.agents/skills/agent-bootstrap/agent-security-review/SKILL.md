---
name: agent-security-review
description: Use when the user invokes Agent Bootstrap command agent-security-review, agent:security-review, or asks Codex to run the security-review agent workflow.
---

# Agent Bootstrap security-review Command

This is a Codex wrapper skill for the canonical command file.

1. Read `.agent/commands/security-review.md`.
2. Treat the user's current request, including any text after `agent-security-review` or `agent:security-review`, as the command arguments or task context.
3. Follow `.agent/commands/security-review.md` exactly.
4. Keep `.agent/commands/security-review.md` as the source of truth; do not edit this wrapper when changing command behavior.
