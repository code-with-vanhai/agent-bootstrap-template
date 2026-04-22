# Changelog

## 0.2.0 - 2026-04-22

- Added canonical command prompts under `core/commands/` for bootstrap, plan, bugfix, implement, review, verify, and release-check.
- Moved Claude Code plugin commands to the canonical `core/commands/` path to avoid root `commands/` drift.
- Added `.agent/commands/` generation for `standard` and `full` bootstrap feature levels.
- Added `core/command-conventions.md` documenting Claude native slash commands and prompt-based `agent:<name>` convention for non-Claude harnesses.
- Added `release-check-workflow.md` for report-only release readiness checks without deploys, tags, pushes, or remote migrations.
- Added `features_enabled`, gate mode metadata, and `security` gate support to generated manifests and gate templates.
- Updated generated adapters for Codex/generic, Cursor, Copilot, and Gemini to document `agent:<name>` command convention; Claude stays native slash only.
- Updated validation to check command files when the commands feature is enabled while remaining compatible with older generated repos without `.agent/commands/`.
- Bumped the Claude plugin and local marketplace metadata to `0.2.0`.
- Added behavior-shaping guardrails to rulebase and gates templates: verification discipline, root-cause-first language, no invented artifacts, and no unrelated changes.
- Updated generated adapters to require re-reading `.agent/rulebase.md` at the start of coding tasks.
- Added optional SessionStart hook template for supported harnesses.
- Added `.agent/runs/<date>-<slug>/spec.md` and `plan.md` convention for non-trivial work.
- Added subagent prompt fragments under `.agent/roles/prompts/` and corresponding template sources under `core/roles/prompts/`.
- Added optional native skill source files under `core/skills/` for supported harnesses.
- Added GitHub-only pull request template source under `core/github/`; other host merge request templates remain a future extension.
- Added optional worktree workflow source under `core/workflows/worktree-workflow.md`.
- Added behavior eval runner and shared eval helpers; evals require the Claude CLI and skip safely when it is missing.
- Added fast behavior evals for verification-before-claim, root-cause-first, and no-invented-gates behavior.
- Added integration behavior eval for scoped changes and no unrelated cleanup.
- Added integration behavior eval for completing script-first bootstrap pending tasks.
- Added deterministic bootstrap skeleton generator with `.agent/bootstrap-pending.md` handoff.
- Added canonical bootstrap steps document to keep script, prompt, and future skills/plugins aligned.
- Added `bootstrap-agent-system` native skill for completing script-first bootstrap safely.
- Added optional Claude Code plugin layer with `.claude-plugin/plugin.json`, local marketplace metadata, `/agent-bootstrap:bootstrap`, and `bin/agent-bootstrap`.
- Extended validation to require role prompt fragments and behavior-shaping guardrails in generated repos.
- Fixed validator root resolution for nested sample repos and explicit `AGENT_ROOT` overrides.

## 1.0.0 - Initial Template

- Added tool-agnostic `.agent/` core templates.
- Added thin adapters for Codex/OpenAI-style agents, Claude, Gemini, Cursor, and Copilot.
- Added role templates for planner, implementer, reviewer, and gate runner.
- Added workflows for bootstrap, feature, bugfix, refactor, review, security review, improvement cycle, and rule evolution.
- Added LLM instantiation prompt and bootstrap checklist.
- Added deterministic validation script for generated repos.
- Added Node.js sample as a few-shot instantiation reference.
- Added source mapping instructions so LLMs copy canonical template files instead of recreating them.
- Simplified manifest audit fields to `instantiated_at` and `llm_tool_used`.
- Added `USAGE.md` with detailed setup, validation, review, and upgrade guidance.
- Added README and usage references to arXiv:2604.15082 with a short description of how the paper maps to this template.
