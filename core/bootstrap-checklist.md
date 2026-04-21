# Bootstrap Checklist

Use this checklist before reporting that agent-system instantiation is complete.

## Repository Facts

- [ ] Stack detected: language, runtime, package/build tool.
- [ ] Package manager detected, or explicitly marked `not applicable`.
- [ ] Test framework detected, or explicitly marked `not configured`.
- [ ] Public surface classified: APIs, CLI, package exports, routes, schemas, config formats, docs usage, or `none found` with scan notes.
- [ ] Dangerous operations listed: deploy, remote migration, destructive data/file operations, secret/key handling, or `none found` with scan notes.
- [ ] Ownership boundaries include at least root-level paths.
- [ ] Monorepo package boundaries captured when applicable.

## Gate Evidence

- [ ] At least one real gate command is configured for code repositories, or all gates are marked `not configured` with evidence for docs/template repos.
- [ ] Every configured gate command was found in a checked-in source: package/build file, Makefile/justfile/Taskfile, CI workflow, or equivalent.
- [ ] No gate command was invented from convention alone.
- [ ] `.agent/gates.md` preserves verification discipline rules: no completion claims without fresh evidence, and no invented gates or commands.
- [ ] `scripts/agent-eval.sh` has valid shell syntax.

## Generated Files

- [ ] `.agent/README.md` exists.
- [ ] `.agent/manifest.json` exists and is valid JSON.
- [ ] `.agent/project-profile.md` exists.
- [ ] `.agent/rulebase.md` exists.
- [ ] `.agent/ownership.md` exists.
- [ ] `.agent/gates.md` exists.
- [ ] `.agent/decisions.md` exists.
- [ ] `.agent/lessons.md` exists.
- [ ] `.agent/rulebase.md` preserves behavior-shaping sections: Discipline Gates, Red Flags, and Rationalization Checks.
- [ ] `.agent/roles/` contains planner, implementer, reviewer, and gate-runner instructions.
- [ ] `.agent/roles/prompts/` contains planner, implementer, reviewer, and gate-runner subagent prompt fragments.
- [ ] `.agent/workflows/` contains bootstrap, feature, bugfix, refactor, review, security review, improvement cycle, and rule evolution workflows.
- [ ] `scripts/agent-eval.sh` exists and is executable when the filesystem supports executable bits.
- [ ] `scripts/agent-validate.sh` exists and is executable when the filesystem supports executable bits.
- [ ] `.agent/runs/*` is not required for bootstrap; create run artifacts only for real non-trivial tasks.

## Adapter Files

Tick only adapters that are intentionally generated or updated.

- [ ] `AGENTS.md`
- [ ] `CLAUDE.md`
- [ ] `GEMINI.md`
- [ ] `.cursor/rules/agent-system.mdc`
- [ ] `.github/copilot-instructions.md`
- [ ] Existing adapter instructions were preserved when still relevant.
- [ ] Adapters are thin and point to `.agent/`.
- [ ] Generated adapters require agents to re-read `.agent/rulebase.md` at the start of any coding task.
- [ ] Optional SessionStart hook is omitted unless explicitly requested, or installed only after confirming the target harness supports it.

## Optional Skills

Tick only when the target harness supports native skill discovery and the user requested skill output.

- [ ] Optional skills were omitted when the target harness does not support them or the user did not request them.
- [ ] If generated, skills were copied from `core/skills/*/SKILL.md`, not recreated from memory.
- [ ] If generated for Codex-style harnesses, skills live under `.agents/skills/agent-bootstrap/<skill>/SKILL.md`.
- [ ] If generated for Claude Code project-local skills, skills live under `.claude/skills/agent-bootstrap/<skill>/SKILL.md` when supported by the user's setup.
- [ ] Generated skills include: verify-before-completion, root-cause-debugging, scoped-implementation, plan-before-code, worktree-isolation, and no-invented-artifacts.
- [ ] Skills remain short behavior-shaping artifacts and do not duplicate full `.agent/` workflows.

## GitHub Metadata

- [ ] Target host was checked from `.github/` or git remotes.
- [ ] `.github/PULL_REQUEST_TEMPLATE.md` was generated if and only if the target repo is GitHub-hosted.
- [ ] If generated, the PR template includes problem observed, evidence, why this belongs here, alternatives, gates run, human review, and single coherent change sections.
- [ ] If skipped, the final report explains the repo is not confirmed GitHub-hosted.

## Placeholder and Drift Checks

- [ ] No `{{PLACEHOLDER}}` tokens remain in generated files.
- [ ] No generated adapter duplicates the full `.agent/rulebase.md`.
- [ ] `.agent/manifest.json` records instantiated template version, timestamp, tool used, and known not-configured gates.
- [ ] `scripts/agent-validate.sh` passes, or every failure is explained.
- [ ] If dispatchable Claude agents were generated from prompt fragments, they preserve inputs, forbidden actions, success criteria, output format, and verification expectation.
- [ ] If optional skills were generated, their names match `core/skills/README.md`.
- [ ] If `.github/PULL_REQUEST_TEMPLATE.md` exists, it includes the fabricated/speculative/bundled-change warning.

## Final Report

- [ ] Files generated or updated are listed.
- [ ] Detected stack is summarized.
- [ ] Configured gates are listed with evidence source.
- [ ] Known not-configured gates are listed.
- [ ] Dangerous operations are listed.
- [ ] Public surface classification is summarized.
- [ ] Human follow-up is explicit.
