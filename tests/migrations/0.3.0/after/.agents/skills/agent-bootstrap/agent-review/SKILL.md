---
name: agent-review
description: Use when the user invokes Agent Bootstrap command agent-review, agent:review, or asks Codex to run the review agent workflow.
---

# Agent Bootstrap review Command

This is a Codex wrapper skill for the canonical command file.

1. Read `.agent/commands/review.md`.
2. Treat the user's current request, including any text after `agent-review` or `agent:review`, as the command arguments or task context.
3. Follow `.agent/commands/review.md` exactly.
4. Keep `.agent/commands/review.md` as the source of truth; do not edit this wrapper when changing command behavior.
