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
- [ ] `.agent/roles/` contains planner, implementer, reviewer, and gate-runner instructions.
- [ ] `.agent/workflows/` contains bootstrap, feature, bugfix, refactor, review, security review, improvement cycle, and rule evolution workflows.
- [ ] `scripts/agent-eval.sh` exists and is executable when the filesystem supports executable bits.
- [ ] `scripts/agent-validate.sh` exists and is executable when the filesystem supports executable bits.

## Adapter Files

Tick only adapters that are intentionally generated or updated.

- [ ] `AGENTS.md`
- [ ] `CLAUDE.md`
- [ ] `GEMINI.md`
- [ ] `.cursor/rules/agent-system.mdc`
- [ ] `.github/copilot-instructions.md`
- [ ] Existing adapter instructions were preserved when still relevant.
- [ ] Adapters are thin and point to `.agent/`.

## Placeholder and Drift Checks

- [ ] No `{{PLACEHOLDER}}` tokens remain in generated files.
- [ ] No generated adapter duplicates the full `.agent/rulebase.md`.
- [ ] `.agent/manifest.json` records instantiated template version, timestamp, tool used, and known not-configured gates.
- [ ] `scripts/agent-validate.sh` passes, or every failure is explained.

## Final Report

- [ ] Files generated or updated are listed.
- [ ] Detected stack is summarized.
- [ ] Configured gates are listed with evidence source.
- [ ] Known not-configured gates are listed.
- [ ] Dangerous operations are listed.
- [ ] Public surface classification is summarized.
- [ ] Human follow-up is explicit.
