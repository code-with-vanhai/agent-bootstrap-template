# Claude Code Instructions

This repository uses `.agent/` as the canonical agent instruction source. **Keep this file as a thin adapter**—do not duplicate the rulebase here.

## Always do

- For any coding task, re-read `.agent/rulebase.md` before planning or editing, even if it was read earlier in the session.
- Before editing, read at least:
  - `.agent/project-profile.md`
  - `.agent/rulebase.md`
  - `.agent/ownership.md`
  - `.agent/gates.md`
  - `.agent/roles/`
  - `.agent/workflows/`
  - `.agent/decisions.md`
  - `.agent/lessons.md`
- Run verification through `scripts/agent-eval.sh` using modes documented in `.agent/gates.md`.
- When the user message starts with `agent:<name>`, read `.agent/commands/<name>.md` and follow it. Treat trailing text as task context or gate mode (prompt convention).

## Ask first

- Destructive operations, large refactors, or cross-boundary edits not covered by the current task.
- Auth, secrets, production deploy, or infrastructure changes.
- Editing `.agent/rulebase.md`, `.agent/gates.md`, or `.agent/ownership.md` for repo-wide policy—follow `.agent/workflows/rule-evolution-workflow.md` and get explicit human approval.

## Never do

- Invent gates, commands, files, or repo facts not evidenced in the repository.
- Claim completion without verification required by `.agent/rulebase.md`.
- Bypass security, validation, authorization, rate limiting, or tests to pass a gate.
- Grow this file into a second rulebase; `.agent/` stays canonical.

## Commands

- Verification: `scripts/agent-eval.sh <mode>` per `.agent/gates.md`.
- Workflows: `agent:<name>` → `.agent/commands/<name>.md`.
