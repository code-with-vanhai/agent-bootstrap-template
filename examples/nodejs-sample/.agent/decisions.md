# Decisions

## 2026-04-21 - Use .agent As Canonical Agent Source

Status: accepted

Context:
- The sample needs one shared rule source for multiple AI tools.

Decision:
- `.agent/` is canonical. `AGENTS.md` stays a thin adapter.

Consequences:
- Do not duplicate long-lived rules in tool-specific adapter files.

