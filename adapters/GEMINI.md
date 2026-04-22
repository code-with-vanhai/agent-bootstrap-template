# Gemini Instructions

This repository uses `.agent/` as the canonical agent instruction source.

## Canonical Instructions

For any coding task, MUST re-read `.agent/rulebase.md` before planning or editing, even if it was read earlier in the session.

Before planning or editing, read:

- `.agent/project-profile.md`
- `.agent/rulebase.md`
- `.agent/ownership.md`
- `.agent/gates.md`
- `.agent/roles/`
- `.agent/workflows/`

Use `scripts/agent-eval.sh` for verification.

## Command Convention

When the user message starts with `agent:<name>`, read `.agent/commands/<name>.md` and follow it.

Treat everything after `agent:<name>` as the task description or gate mode. This is a prompt convention, not a native slash command.

## Operating Rules

Do not duplicate long-lived rules in this file.
