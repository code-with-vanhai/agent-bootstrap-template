---
description: Create a scoped spec and implementation plan before making code changes.
argument-hint: <task description>
---

# Plan

Read `.agent/rulebase.md`, `.agent/project-profile.md`, `.agent/ownership.md`, `.agent/gates.md`, `.agent/decisions.md`, and relevant `.agent/workflows/`.

Task: $ARGUMENTS

If invoked as `agent:plan <desc>` in a non-Claude harness, treat the text after `agent:plan` as the task description.

Follow `.agent/workflows/feature-workflow.md`, but execute planning only:

1. Define the goal, affected areas, owner, acceptance criteria, and verification gate.
2. For non-trivial work, create `.agent/runs/<date>-<slug>/spec.md` and `.agent/runs/<date>-<slug>/plan.md`.
3. For trivial work, write the plan inline only if it meets the repo's trivial-change rule.
4. Use only gates documented in `.agent/gates.md` and `scripts/agent-eval.sh`.
5. Stop before editing product code.

If the task is ambiguous enough that a plan would be speculative, ask one concise clarification question.
