# Copilot Instructions

This repository uses a shared agent system in `.agent/`.

## Canonical Instructions

For any coding task, MUST re-read `.agent/rulebase.md` before planning or editing, even if it was read earlier in the session.

Use the following files as the source of truth:

- `.agent/project-profile.md`
- `.agent/rulebase.md`
- `.agent/ownership.md`
- `.agent/gates.md`
- `.agent/decisions.md`
- `.agent/lessons.md`

## Command Convention

When the user message starts with `agent:<name>`, read `.agent/commands/<name>.md` and follow it.

Treat everything after `agent:<name>` as the task description or gate mode. This is a prompt convention, not a native slash command.

## Operating Rules

Prefer existing project patterns. Do not suggest changes that bypass security, validation, authorization, rate limiting, tests, or public contracts.
