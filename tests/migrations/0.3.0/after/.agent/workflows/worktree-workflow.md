# Worktree Workflow

Worktrees are optional acceleration, not required process. Use them only when isolation helps the task and the repository workflow supports it.

## When To Use

Use this workflow when one of these opt-in triggers applies:

- Multi-file feature work.
- Work estimated at 2 hours or more.
- Risky refactor or broad investigation.
- Parallel agent work that needs isolated branches.
- Hotfix needs to merge while the current branch is dirty.
- User explicitly asks for an isolated workspace.

## When NOT To Use

Do not create a worktree when:

- The task is a single-file fix or small documentation update.
- The team uses a strict branch-per-PR and CI-heavy workflow where local worktrees add no value.
- The repository has complex submodules, generated worktrees, or tooling that may conflict with `git worktree`.
- The working tree or branch state is unclear and cannot be inspected safely.
- The user asks not to use worktrees.

## Directory Priority

Choose the worktree parent directory in this order:

1. Existing `.worktrees/` directory.
2. Existing `worktrees/` directory.
3. Explicit path from project instructions, user request, or existing repo convention.
4. Ask the user where worktrees should live.

For project-local directories, verify the directory is ignored before creating a worktree:

```bash
git check-ignore -q .worktrees 2>/dev/null || git check-ignore -q worktrees 2>/dev/null
```

If the selected project-local directory is not ignored, update `.gitignore` or ask for direction before creating the worktree.

## Setup Steps

1. Inspect current branch and working-tree status.
2. Select a branch name that matches the task.
3. Select the worktree directory using the directory priority above.
4. Verify project-local worktree directory ignore coverage.
5. Create the worktree with `git worktree add`.
6. Install or prepare dependencies only through repo-documented setup commands.
7. Run the baseline gate from `.agent/gates.md` before implementing.

## Baseline Gate

Before editing inside the worktree:

- Run the narrowest configured baseline gate, usually `scripts/agent-eval.sh fast`.
- If the baseline gate fails, record the failure before making task changes.
- Do not hide pre-existing failures.
- Do not claim the worktree is ready without fresh baseline evidence.

## Implementation

Inside the worktree:

- Re-read `.agent/rulebase.md`, `.agent/ownership.md`, and the relevant workflow.
- Keep the task scoped to the branch purpose.
- Do not use isolation as permission for unrelated refactors.
- Run the selected gate before reporting completion.

## Cleanup

When implementation is complete:

1. Verify the relevant gate result.
2. Decide whether to merge, rebase, open a PR, keep the branch, or discard the work.
3. Remove the worktree only after useful changes are safely merged, pushed, or intentionally discarded.
4. Run `git worktree prune` only when it is safe and does not affect user work.

## Safety Rules

- Never delete or overwrite user changes while preparing a worktree.
- Never create a project-local worktree directory unless it is ignored.
- Never run deploys, remote migrations, destructive commands, or secret-changing operations from this workflow without explicit human approval.
- If worktree creation fails because of environment or permissions, fall back to the current workspace and report the limitation.
