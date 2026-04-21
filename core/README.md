# Agent System

This directory is the canonical instruction source for coding agents working in this repository.

Agents must read these files before making changes:

- `project-profile.md`: what the project is, how it is structured, and which docs matter.
- `rulebase.md`: safety rules, required practices, and forbidden actions.
- `ownership.md`: which role owns which paths and when coordination is required.
- `gates.md`: verification commands and acceptance criteria.
- `roles/`: role-specific behavior.
- `workflows/`: feature, bugfix, refactor, review, and bootstrap procedures.
- `workflows/improvement-cycle-workflow.md`: metric-driven candidate/champion improvement loop.
- `workflows/security-review-workflow.md`: focused security review for auth, data, secrets, and trust boundaries.
- `workflows/rule-evolution-workflow.md`: controlled process for updating agent rules.
- `decisions.md`: architecture decisions that must be preserved.
- `lessons.md`: repo-specific lessons learned from previous incidents and reviews.

When instantiating this template into a new repository, use `core/instantiation-prompt.md` and `core/bootstrap-checklist.md` from the template repo. Generated target repos do not need to keep those two files unless the team wants bootstrap instructions checked in.

Tool-specific instruction files such as `AGENTS.md`, `CLAUDE.md`, Cursor rules, Gemini instructions, or Copilot instructions must not duplicate long rules. They should point back to this directory.

## Operating Model

1. Bootstrap knowledge before editing.
2. Identify the correct workflow.
3. Assign ownership by path and subsystem.
4. Make scoped changes.
5. Run the appropriate gate through `scripts/agent-eval.sh`.
6. Review the diff against `rulebase.md`, `ownership.md`, and `decisions.md`.
7. Record new durable lessons in `lessons.md` only when they prevent future mistakes.

## Acceptance Model

A change is acceptable only when:

- The requested behavior is implemented.
- The diff stays inside the intended ownership boundary or explicitly documents coordination.
- The selected verification gate passes, or any unrun gate is clearly explained.
- Public contracts, schemas, docs, and tests are updated when behavior changes.
- No forbidden action from `rulebase.md` was taken.
