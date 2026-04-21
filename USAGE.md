# Usage Guide

This guide explains how to use `agent-bootstrap-template` to add a tool-agnostic agent system to an existing repository.

## Goal

The generated target repo should have:

```text
.agent/                  # canonical agent instructions
.agent/roles/prompts/    # prompt fragments for delegated agent work
scripts/agent-eval.sh    # repo-specific verification gates
scripts/agent-validate.sh # mechanical validation guardrail
AGENTS.md / CLAUDE.md / Cursor rules / other thin adapters
```

`.agent/` is the source of truth. Tool-specific adapters should stay thin and point back to `.agent/`.

## Research Reference

This workflow is based on a practical adaptation of:

- "Autonomous Evolution of EDA Tools: Multi-Agent Self-Evolved ABC", arXiv:2604.15082.
- PDF: https://arxiv.org/pdf/2604.15082
- Local notes: `core/research-basis.md`

The paper uses specialized agents, repository profiling, correctness checks, QoR evaluation, and a self-evolving rulebase to improve a large EDA codebase. This template keeps the useful engineering pattern but applies it conservatively: agents prepare scoped patches, run repo-specific gates, and keep rule changes explicit and reviewable.

## Recommended Workflow

1. Put this template next to the target repository.
2. Ask your LLM coding tool to read `core/instantiation-prompt.md`.
3. Let the LLM scan the target repo and generate `.agent/`.
4. Run validation in the target repo.
5. Review the generated diff before committing.

## Prompt To Use

From inside the target repository, send this to your coding agent:

```text
Setup Agent Bootstrap Kit for this repo.

Use the agent-bootstrap-template located at: /path/to/agent-bootstrap-template

Read core/instantiation-prompt.md first and follow it exactly.

Requirements:
- Scan the repo before generating files.
- Create .agent/ as the canonical instruction source.
- Create scripts/agent-eval.sh and scripts/agent-validate.sh.
- Create thin adapters for common tools unless existing adapters should be preserved.
- Configure gate commands only if they are found in package/build files, Makefile/justfile/Taskfile, CI workflows, or equivalent checked-in files.
- Mark unknown gates as not configured instead of inventing commands.
- Do not modify business logic.
- Do not deploy.
- Do not run remote migrations.
- Do not edit secrets or env values.
```

Replace `/path/to/agent-bootstrap-template` with the actual path.

## What The LLM Should Generate

Expected target layout:

```text
repo/
├── .agent/
│   ├── README.md
│   ├── manifest.json
│   ├── project-profile.md
│   ├── rulebase.md
│   ├── ownership.md
│   ├── gates.md
│   ├── decisions.md
│   ├── lessons.md
│   ├── roles/
│   │   └── prompts/
│   ├── runs/              # created only for non-trivial task specs/plans
│   └── workflows/
├── scripts/
│   ├── agent-eval.sh
│   └── agent-validate.sh
├── AGENTS.md
├── CLAUDE.md
├── GEMINI.md
├── .cursor/rules/agent-system.mdc
└── .github/copilot-instructions.md
```

Adapters may be omitted if the repo does not use that tool, but any generated adapter must point to `.agent/`.

## Validation

Run this from the target repo:

```bash
bash scripts/agent-validate.sh
```

The validator checks:

- Required `.agent/` files exist.
- Role, role prompt, and workflow files exist.
- Behavior-shaping guardrails exist in `.agent/rulebase.md` and `.agent/gates.md`.
- No `{{PLACEHOLDER}}` tokens remain.
- `.agent/manifest.json` is valid JSON.
- `scripts/agent-eval.sh` has valid shell syntax.
- Generated adapters point to `.agent/`.

Then run a configured gate when appropriate:

```bash
bash scripts/agent-eval.sh fast
```

If a gate is marked `not configured`, do not treat that as a failure by itself. Review whether the LLM correctly scanned the repo and documented why no command exists.

## Review Checklist

Before committing the generated files, review:

- `project-profile.md`: stack, package manager, docs, contracts, dangerous operations.
- `rulebase.md`: forbidden actions and required practices match the repo.
- `ownership.md`: root paths and monorepo packages are assigned correctly.
- `gates.md`: every configured command exists in checked-in repo files.
- `scripts/agent-eval.sh`: no deploy or remote migration commands run automatically.
- Adapters: thin and pointing to `.agent/`.
- Adapters: require agents to re-read `.agent/rulebase.md` at the start of any coding task.
- Prompt fragments: `.agent/roles/prompts/` includes planner, implementer, reviewer, and gate-runner subagent prompts.
- Run artifacts: `.agent/runs/*` is absent or contains only real task specs/plans; empty placeholder runs are not required.
- Optional hooks: omitted unless intentionally enabled for a supported harness.
- `manifest.json`: includes `instantiated_at`, `llm_tool_used`, and `known_not_configured_gates`.

## Handling Missing Gates

Use `not configured` when no real command exists.

Good:

```md
E2E gate: not configured
Reason: scanned package.json, Makefile, and .github/workflows; no e2e framework or command found.
```

Bad:

```md
E2E gate: npm run e2e
```

unless `npm run e2e` actually exists.

## Updating Existing Adapter Files

If the target repo already has `AGENTS.md`, `CLAUDE.md`, Cursor rules, or Copilot instructions:

- Preserve important repo-specific rules.
- Remove duplicated long rule blocks when they now belong in `.agent/`.
- Add a clear pointer to `.agent/`.
- Do not let adapter files drift from each other.

## Upgrade Policy

When this template changes:

1. Read `CHANGELOG.md`.
2. Apply only relevant updates to the target repo.
3. Review the diff manually.
4. Run:

```bash
bash scripts/agent-validate.sh
```

Do not use automatic migration scripts for agent rules unless a future incident proves they are necessary.

## Example

See:

```text
examples/nodejs-sample/
```

This sample shows a filled `.agent/` directory, multiple thin adapters, configured Node.js gates, not-configured gates, and a passing validation script.
