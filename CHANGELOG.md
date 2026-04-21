# Changelog

## Unreleased

- Added behavior-shaping guardrails to rulebase and gates templates: verification discipline, root-cause-first language, no invented artifacts, and no unrelated changes.
- Updated generated adapters to require re-reading `.agent/rulebase.md` at the start of coding tasks.
- Added optional SessionStart hook template for supported harnesses.
- Added `.agent/runs/<date>-<slug>/spec.md` and `plan.md` convention for non-trivial work.
- Added subagent prompt fragments under `.agent/roles/prompts/` and corresponding template sources under `core/roles/prompts/`.
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
