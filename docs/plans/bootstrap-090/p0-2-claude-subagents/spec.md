# Spec: Claude Native Subagents (P0-2)

**Status:** Verified with evidence: agent-validate.sh @ 2026-04-29T03:59:48Z (exit=0)
**Date:** 2026-04-29
**Ref commit:** `c525be4` (pre-implementation reference; impl landed in working tree)
**Plan location note:** Stored under `docs/plans/bootstrap-090/p0-2-claude-subagents/` because this template repo dogfoods plans under `docs/plans/`, not `.agent/runs/`. Generated target repos should use `.agent/runs/<date>-<slug>/`.
**Track:** 0.9.0 P0-2, after P0-1 commit `c525be4`.

## Problem

Claude harnesses currently get `.agent/roles/prompts/*-subagent.md` prompt fragments and `.claude/skills/agent-bootstrap/*/SKILL.md` files when `--features full` is selected, but they do not get native `.claude/agents/<role>.md` files. The manual bootstrap guidance still tells users to adapt the prompt fragments themselves.

This leaves a high-value Claude Code feature unused and adds manual conversion work for every target repository that wants dispatchable planner, implementer, reviewer, or gate-runner agents.

## Goals

- Generate native `.claude/agents/planner.md`, `implementer.md`, `reviewer.md`, and `gate-runner.md` only when `--harness claude --features full`.
- Preserve `.agent/roles/prompts/*-subagent.md` as canonical prompt fragments.
- Do not generate Claude agents for `generic`, `codex`, `cursor`, `copilot`, or `gemini`.
- Add a `claude-native-subagents` feature marker to `.agent/manifest.json` only when those files are generated.
- Validate generated repos that declare `claude-native-subagents`.
- Avoid pinning `model` in generated agent frontmatter; repo owners can choose model policy later.

## Non-Goals

- No MCP server configuration.
- No hook registration.
- No `.claude/settings.json` edits.
- No changes to command prompts or base skills.
- No implementation in this spec/plan turn.

## Expected Generated Files

For `--harness claude --features full`:

```text
.claude/agents/planner.md
.claude/agents/implementer.md
.claude/agents/reviewer.md
.claude/agents/gate-runner.md
```

Each file should prepend Claude subagent frontmatter to the existing prompt fragment body from `core/roles/prompts/<role>-subagent.md`.

## Frontmatter Contract

Use only stable, file-based subagent frontmatter fields:

- `name`
- `description`
- `tools`
- `disallowedTools`
- `permissionMode`
- `maxTurns`
- `skills`

Do not emit `model`: the field is supported, but the template should not pin it because model availability and budget policy are repo-specific.

## Role Matrix

| Role | tools | disallowedTools | permissionMode | maxTurns | skills |
|---|---|---|---|---|---|
| `planner` | `Read, Grep, Glob, Bash` | `Edit, Write, MultiEdit` | `plan` | `30` | `plan-before-code, no-invented-artifacts` |
| `implementer` | `Read, Edit, Write, MultiEdit, Grep, Glob, Bash` | none | `default` | `60` | `scoped-implementation, no-invented-artifacts, no-secret-leakage` |
| `reviewer` | `Read, Grep, Glob, Bash` | `Edit, Write, MultiEdit` | `default` | `40` | `verify-before-completion, no-invented-artifacts` |
| `gate-runner` | `Read, Bash` | `Edit, Write, MultiEdit` | `default` | `20` | `verify-before-completion` |

Planner receives `Bash` so it can run read-only git and hashing commands required for evidence blocks, while `permissionMode: plan` plus denied write tools keeps it from editing.

## Validation Expectations

- `scripts/agent-validate.sh` must pass in the source template.
- Generated Claude full fixture validation must pass and assert the four native agent files exist.
- Generated Codex full fixture validation must continue to pass and must not expect `.claude/agents`.
- `scripts/agent-validate-plan.sh --force --strict docs/plans/bootstrap-090/p0-2-claude-subagents` must pass before implementation starts.
