---
name: worktree-isolation
description: Use when starting multi-file feature work, risky refactors, hotfixes while the current branch is dirty, or parallel agent work that benefits from isolated branches.
---

# Worktree Isolation

Worktrees are optional acceleration, not a universal requirement.

## Use When

- Multi-file feature work.
- Risky refactor or broad investigation.
- Hotfix needs to merge while the current branch is dirty.
- Parallel agents need separate branches.
- The user explicitly asks for isolated work.

## Safety Rules

- Check whether the repo already has a worktree convention before creating one.
- Verify project-local worktree directories are ignored before use.
- Do not force worktrees on teams that use branch-and-CI workflow only.
- Never abandon or delete user work while preparing isolation.

## Red Flags

- Creating `.worktrees/` without checking `.gitignore`.
- Starting broad work on `main` with a dirty tree.
- Using worktrees to avoid understanding ownership boundaries.
- Treating optional isolation as permission for larger diffs.

## Canonical Sources

- `.agent/workflows/worktree-workflow.md` when enabled
- `.agent/ownership.md`
- `.agent/rulebase.md`
