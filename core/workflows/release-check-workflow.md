# Release Check Workflow

Use this workflow for release-readiness review before merging, tagging, or publishing.

This workflow is report-only. It must not deploy, tag, push, publish, run remote migrations, rotate secrets, or mutate production state.

## Scope

1. Read `.agent/project-profile.md`, `.agent/gates.md`, `.agent/decisions.md`, and recent relevant release notes.
2. Identify the intended release branch, target version, and release surface from the user request or checked-in repo conventions.
3. Check local git state:
   - Current branch.
   - Uncommitted changes.
   - Recent commits relevant to the release.
   - Divergence from the configured release branch when that branch is known.
4. Check release notes:
   - `CHANGELOG.md`, release notes, or equivalent docs have an `Unreleased` entry or a target-version entry when the repo uses release notes.
   - If the repo has no release-note convention, report `not configured`.
5. Run all configured gates needed for release readiness:
   - Prefer `scripts/agent-eval.sh release` when configured.
   - Otherwise run `scripts/agent-eval.sh full` when configured.
   - Add domain gates such as `security`, `e2e`, `frontend`, or `backend` only when `.agent/gates.md` marks them configured and the release surface requires them.
6. Report blockers, skipped checks, and residual risk.

## Output

```md
Release check:
- Target:
- Branch:
- Working tree:
- Release notes:
- Gates:
- Blockers:
- Skipped:
- Residual risk:
```

## Do Not

- Do not deploy.
- Do not tag.
- Do not push.
- Do not publish packages.
- Do not run remote migrations.
- Do not edit secrets or environment values.
