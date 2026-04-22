# Bootstrap Steps

This is the canonical bootstrap flow for adding Agent Bootstrap Kit to a target repository.

Use this file as the source of truth when updating:

- `core/instantiation-prompt.md`
- `scripts/bootstrap-request.sh`
- `core/skills/bootstrap-agent-system/SKILL.md`
- Claude Code plugin files under `.claude-plugin/`, `commands/`, and `bin/`

## Phase 1: Deterministic Skeleton

The bootstrap script should perform mechanical work that does not require model judgment:

1. Resolve the target repository.
2. Resolve feature and harness choices.
3. Create the baseline `.agent/` structure.
4. Copy canonical template files from `core/`, `adapters/`, and `scripts/`.
5. Replace known placeholders with conservative, non-invented values.
6. Copy optional outputs only when selected or clearly detected:
   - GitHub PR template for GitHub-hosted repositories when features are `standard` or `full`.
   - Native skills when features are `full` and the harness has a supported skill layout.
   - Worktree workflow when features are `full`.
   - SessionStart hook only when explicitly requested.
7. Create `.agent/bootstrap-pending.md` with the remaining repo-specific tasks for the agent.

The deterministic phase must not modify business logic, install dependencies, run deploys, run remote migrations, or invent repository facts.

## Phase 2: Agent Completion

The agent should complete only the parts that require repository understanding:

1. Read `.agent/bootstrap-pending.md`.
2. Scan checked-in repository files before editing generated agent files.
3. Fill `.agent/project-profile.md` with observed stack, runtime, public surface, dangerous operations, and repository map.
4. Fill `.agent/gates.md` and `scripts/agent-eval.sh` only with commands found in package/build files, task files, or CI.
5. Fill `.agent/ownership.md` with real path boundaries.
6. Fill `.agent/manifest.json` with confirmed project metadata.
7. Preserve existing adapter instructions when relevant.
8. Run `bash scripts/agent-validate.sh`.
9. Delete `.agent/bootstrap-pending.md` only after the generated agent system is complete.

Unknown facts must remain `not confirmed` or `not configured`. Do not use package-manager or framework convention as evidence.

## Features

`minimal`:

- Baseline `.agent/`
- `scripts/agent-eval.sh`
- `scripts/agent-validate.sh`
- Harness adapter files

`standard`:

- Everything in `minimal`
- GitHub PR template when the target is confirmed GitHub-hosted

`full`:

- Everything in `standard`
- Native skills when supported by the selected harness
- Optional worktree workflow

SessionStart hooks are never installed by feature level alone. They require an explicit hook flag and a supported harness.

## Claude Code Plugin Layer

The Claude Code plugin is an optional first-run convenience layer. It must not replace the deterministic script or the repository-local `.agent/` source of truth.

Plugin behavior:

- `.claude-plugin/plugin.json` points Claude Code to `./core/skills/` and `./commands/`.
- `commands/bootstrap.md` exposes `/agent-bootstrap:bootstrap` for explicit setup.
- `bin/agent-bootstrap` wraps `scripts/bootstrap-request.sh` with `--template <plugin-root>` and default `--harness claude`.
- The plugin may make `bootstrap-agent-system` discoverable before a target repo has `.agent/`.
- The plugin must not install SessionStart hooks by default.

After the plugin creates `.agent/bootstrap-pending.md`, Phase 2 remains unchanged: the agent completes only repo-specific facts, gates, ownership, and manifest fields from checked-in evidence.

## Harnesses

`generic`:

- Generate `AGENTS.md`
- Do not generate native skills

`codex`:

- Generate `AGENTS.md`
- In `full`, generate skills under `.agents/skills/agent-bootstrap/`

`claude`:

- Generate `AGENTS.md` and `CLAUDE.md`
- In `full`, generate skills under `.claude/skills/agent-bootstrap/`

`cursor`:

- Generate `AGENTS.md` and `.cursor/rules/agent-system.mdc`

`copilot`:

- Generate `AGENTS.md` and `.github/copilot-instructions.md`

`gemini`:

- Generate `AGENTS.md` and `GEMINI.md`
