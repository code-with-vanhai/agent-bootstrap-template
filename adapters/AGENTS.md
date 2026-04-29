# Agent Instructions

This repository uses a shared, tool-agnostic agent system. **Canonical instructions live in `.agent/`**—this file only prioritizes behavior; do not treat it as a second rulebase.

## Always do

- For any coding task, re-read `.agent/rulebase.md` before planning or editing, even if it was read earlier in the session.
- Before making changes, read at least:
  - `.agent/project-profile.md`
  - `.agent/rulebase.md`
  - `.agent/ownership.md`
  - `.agent/gates.md`
  - `.agent/roles/`
  - `.agent/workflows/`
  - `.agent/decisions.md`
  - `.agent/lessons.md`
- Run verification through `scripts/agent-eval.sh` using modes documented in `.agent/gates.md`.
- When the user message starts with `agent:<name>`, read `.agent/commands/<name>.md` and follow it. Treat everything after `agent:<name>` as the task description or gate mode (prompt convention, not necessarily a native slash command).

## Ask first

- Destructive or data-loss operations, broad refactors outside the stated scope, or edits that might violate `.agent/ownership.md`.
- Auth, credentials, production deploy, infrastructure, or changes with legal/security/compliance impact.
- Editing `.agent/rulebase.md`, `.agent/gates.md`, or `.agent/ownership.md` for repo-wide policy—follow `.agent/workflows/rule-evolution-workflow.md` and get explicit human approval.

## Never do

- Invent gates, commands, files, frameworks, APIs, or ownership boundaries.
- Claim work complete without fresh verification evidence required by `.agent/rulebase.md`.
- Bypass security, validation, authorization, rate limiting, or tests to make a gate pass.
- Copy long-lived rules here instead of `.agent/`—keep this adapter thin.

## Commands

- Verification: `scripts/agent-eval.sh <mode>` per `.agent/gates.md` and `.agent/commands/verify.md`.
- Agent workflows: `agent:<name>` → `.agent/commands/<name>.md`.
