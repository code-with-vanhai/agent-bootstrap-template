# Agent Instructions

This repository uses a shared, tool-agnostic agent system.

## Canonical Instructions

For any coding task, MUST re-read `.agent/rulebase.md` before planning or editing, even if it was read earlier in the session.

Before making changes, read:

- `.agent/project-profile.md`
- `.agent/rulebase.md`
- `.agent/ownership.md`
- `.agent/gates.md`
- `.agent/roles/`
- `.agent/workflows/`
- `.agent/decisions.md`
- `.agent/lessons.md`

Use `scripts/agent-eval.sh` for verification gates.

## Command Convention

When the user message starts with `agent:<name>`, read `.agent/commands/<name>.md` and follow it.

Treat everything after `agent:<name>` as the task description or gate mode. This is a prompt convention, not a native slash command.

## Operating Rules

Do not duplicate long-lived rules in this file. The canonical source is `.agent/`.
