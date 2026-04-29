# Gemini Instructions

This repository uses `.agent/` as the canonical agent instruction source. **This file is a thin adapter**; long-lived rules belong under `.agent/`.

## Always do

- For any coding task, re-read `.agent/rulebase.md` before planning or editing, even if it was read earlier in the session.
- Before planning or editing, read at least:
  - `.agent/project-profile.md`
  - `.agent/rulebase.md`
  - `.agent/ownership.md`
  - `.agent/gates.md`
  - `.agent/roles/`
  - `.agent/workflows/`
  - `.agent/decisions.md`
  - `.agent/lessons.md`
- Run verification through `scripts/agent-eval.sh` per `.agent/gates.md`.
- When the user message starts with `agent:<name>`, read `.agent/commands/<name>.md` and follow it. Treat trailing text as task context or gate mode (prompt convention).

## Ask first

- Destructive changes, risky migrations, or ownership-boundary violations.
- Auth, secrets, production or infrastructure impact.
- Editing `.agent/rulebase.md`, `.agent/gates.md`, or `.agent/ownership.md` for repo-wide policy—use `.agent/workflows/rule-evolution-workflow.md` and explicit human approval.

## Never do

- Invent gates, commands, or untracked repo facts.
- Claim completion without evidence required by `.agent/rulebase.md`.
- Bypass security, validation, authorization, rate limiting, or tests.
- Duplicate `.agent/` rules at length here.

## Commands

- Gates: `scripts/agent-eval.sh <mode>` per `.agent/gates.md`.
- `agent:<name>` → `.agent/commands/<name>.md`.
