# Copilot Instructions

This repository uses a shared agent system in `.agent/`. **Copilot reads this file first—keep it thin and point back to `.agent/`.**

## Always do

- For any coding task, re-read `.agent/rulebase.md` before planning or editing, even if it was read earlier in the session.
- Use these files as the source of truth before suggesting edits:
  - `.agent/project-profile.md`
  - `.agent/rulebase.md`
  - `.agent/ownership.md`
  - `.agent/gates.md`
  - `.agent/decisions.md`
  - `.agent/lessons.md`
- Prefer existing project patterns; align suggestions with checked-in conventions.
- When the user message starts with `agent:<name>`, read `.agent/commands/<name>.md` and follow it. Treat trailing text as task context or gate mode (prompt convention).

## Ask first

- Destructive edits, risky refactors, or cross-cutting changes beyond the request.
- Security-sensitive areas (auth, secrets, crypto), production deploy, or compliance-facing behavior.
- Editing `.agent/rulebase.md`, `.agent/gates.md`, or `.agent/ownership.md` for policy—use `.agent/workflows/rule-evolution-workflow.md` and explicit human approval.

## Never do

- Suggest changes that bypass security, validation, authorization, rate limiting, tests, or public contracts.
- Invent gates, commands, or undocumented repo facts.
- Claim a change is production-ready without the verification discipline in `.agent/rulebase.md`.
- Replace `.agent/` with a long fork of rules in this file.

## Commands

- Verification: `scripts/agent-eval.sh <mode>` as documented in `.agent/gates.md`.
- `agent:<name>` → `.agent/commands/<name>.md`.
