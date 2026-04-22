# Usage Guide

This guide explains how to use `agent-bootstrap-template` to add a tool-agnostic agent system to an existing repository.

## Goal

The generated target repo should have these baseline files:

```text
.agent/                  # canonical agent instructions
.agent/roles/prompts/    # prompt fragments for delegated agent work
scripts/agent-eval.sh    # repo-specific verification gates
scripts/agent-validate.sh # mechanical validation guardrail
AGENTS.md / CLAUDE.md / Cursor rules / other thin adapters
```

`.agent/runs/` is created only when a real non-trivial task needs spec and plan artifacts; it is not required at bootstrap.

`.agent/` is the source of truth. Tool-specific adapters should stay thin and point back to `.agent/`.

Generated rulebase and gates files include behavior-shaping guardrails:

- no completion claims without fresh verification evidence
- no fixes without root-cause investigation
- no invented commands, files, functions, gates, or repo facts
- no unrelated changes bundled into the task
- rationalization checks that turn common agent excuses into explicit stop signs

Native skill output is optional. When the target harness supports skills and the user requests them, copy skills from `core/skills/`; otherwise omit skill files.

Worktree workflow output is optional. Generate it only when the user opts into worktree-based isolation.

GitHub PR template output is conditional. Generate `.github/PULL_REQUEST_TEMPLATE.md` only for repos confirmed to be GitHub-hosted.

SessionStart hook output is optional. Install hook files only when the user explicitly requests harness-level context injection and the target harness supports it.

## Research Reference

This workflow is based on a practical adaptation of:

- "Autonomous Evolution of EDA Tools: Multi-Agent Self-Evolved ABC", arXiv:2604.15082.
- PDF: https://arxiv.org/pdf/2604.15082
- Local notes: `core/research-basis.md`

The paper uses specialized agents, repository profiling, correctness checks, QoR evaluation, and a self-evolving rulebase to improve a large EDA codebase. This template keeps the useful engineering pattern but applies it conservatively: agents prepare scoped patches, run repo-specific gates, and keep rule changes explicit and reviewable.

## Recommended Workflow

1. Put this template next to the target repository.
2. Run `scripts/bootstrap-request.sh` from this template against the target repo.
3. Ask your LLM coding tool to complete `.agent/bootstrap-pending.md`.
4. Run validation in the target repo.
5. Review the generated diff before committing.

## One-Line Setup

From inside the target repository:

```bash
/path/to/agent-bootstrap-template/scripts/bootstrap-request.sh \
  --features standard \
  --harness claude \
  --target .
```

Then tell your coding agent:

```text
Complete .agent/bootstrap-pending.md
```

Replace `/path/to/agent-bootstrap-template` with the actual path.

Feature levels:

- `minimal`: baseline `.agent/`, verification scripts, and selected harness adapters.
- `standard`: `minimal` plus GitHub PR template when the repo is confirmed GitHub-hosted.
- `full`: `standard` plus supported native skills and the optional worktree workflow.

Harness options:

- `generic`: `AGENTS.md`
- `codex`: `AGENTS.md`; with `full`, skills go to `.agents/skills/agent-bootstrap/`
- `claude`: `AGENTS.md` and `CLAUDE.md`; with `full`, skills go to `.claude/skills/agent-bootstrap/`
- `cursor`: `AGENTS.md` and `.cursor/rules/agent-system.mdc`
- `copilot`: `AGENTS.md` and `.github/copilot-instructions.md`
- `gemini`: `AGENTS.md` and `GEMINI.md`

Hooks are never installed by feature level alone. Use `--install-hook` only after confirming the target harness supports the SessionStart hook shape.

## Manual Prompt Fallback

If you do not want to run the deterministic bootstrap script, send this from inside the target repository:

```text
Setup Agent Bootstrap Kit for this repo.

Use the agent-bootstrap-template located at: /path/to/agent-bootstrap-template

Read core/instantiation-prompt.md first and follow it exactly.

Requirements:
- Scan the repo before generating files.
- Create .agent/ as the canonical instruction source.
- Create scripts/agent-eval.sh and scripts/agent-validate.sh.
- Create thin adapters for common tools unless existing adapters should be preserved.
- Preserve behavior-shaping sections in rulebase and gates.
- Create .agent/roles/prompts/ subagent prompt fragments.
- Do not create .agent/runs/* during bootstrap unless there is a real non-trivial task to plan.
- Generate optional skills only if the target harness supports native skill discovery and skill output is requested.
- Generate optional worktree workflow only if requested or already documented by the repo.
- Generate `.github/PULL_REQUEST_TEMPLATE.md` only if the repo is GitHub-hosted.
- Install optional SessionStart hooks only if explicitly requested.
- Configure gate commands only if they are found in package/build files, Makefile/justfile/Taskfile, CI workflows, or equivalent checked-in files.
- Mark unknown gates as not configured instead of inventing commands.
- Do not modify business logic.
- Do not deploy.
- Do not run remote migrations.
- Do not edit secrets or env values.
```

The script-first flow is preferred because it lets shell code handle deterministic file copy and leaves the model to complete only repo-specific facts.

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
│   │   ├── planner.md
│   │   ├── implementer.md
│   │   ├── reviewer.md
│   │   ├── gate-runner.md
│   │   └── prompts/
│   │       ├── planner-subagent.md
│   │       ├── implementer-subagent.md
│   │       ├── reviewer-subagent.md
│   │       └── gate-runner-subagent.md
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

Optional generated skill layouts:

```text
.agents/skills/agent-bootstrap/<skill>/SKILL.md
.claude/skills/agent-bootstrap/<skill>/SKILL.md
```

Use only the layout supported by the user's tool setup.

Optional generated files:

```text
.agent/bootstrap-pending.md                # created by bootstrap-request.sh until agent completion
.agent/workflows/worktree-workflow.md       # only when worktree isolation is requested
.github/PULL_REQUEST_TEMPLATE.md            # only for GitHub-hosted repos
harness-specific SessionStart hook path      # only when explicitly requested
```

## Operating Rules For Generated Repos

Agents using a generated repo should follow these rules:

- Re-read `.agent/rulebase.md` at the start of any coding task.
- Use `.agent/project-profile.md` for repo facts and `.agent/gates.md` for gate commands.
- Treat every unknown command or gate as `not configured` until found in checked-in files.
- For trivial work, inline planning is acceptable when all of these are true: two files or fewer, 30 changed lines or fewer, no public contract change, and no schema change.
- For non-trivial work, create `.agent/runs/<date>-<slug>/spec.md` and `plan.md` before editing.
- When in doubt, write the plan. When the heuristic and engineering judgment conflict, engineering judgment wins.
- Report fresh verification evidence before saying work is complete.
- Link meaningful run artifacts from `.agent/decisions.md` or `.agent/lessons.md` when they affect future work.

## Validation

Run this from the target repo:

```bash
bash scripts/agent-validate.sh
```

The validator checks:

- Required `.agent/` files exist.
- `.agent/bootstrap-pending.md` may exist during initial setup; delete it after agent completion.
- Role, role prompt, and workflow files exist.
- Behavior-shaping guardrails exist in `.agent/rulebase.md` and `.agent/gates.md`.
- No `{{PLACEHOLDER}}` tokens remain.
- `.agent/manifest.json` is valid JSON.
- `scripts/agent-eval.sh` has valid shell syntax.
- Generated adapters point to `.agent/`.
- Optional GitHub PR template and worktree workflow are validated only when present.

The same script also supports template-source validation. When run from this repository root, it validates source files such as `core/skills/`, `core/github/PULL_REQUEST_TEMPLATE.md`, and `core/workflows/worktree-workflow.md`.

Then run a configured gate when appropriate:

```bash
bash scripts/agent-eval.sh fast
```

If a gate is marked `not configured`, do not treat that as a failure by itself. Review whether the LLM correctly scanned the repo and documented why no command exists.

## Testing Agent Behavior

This template also includes optional behavior evals for the template itself:

```bash
scripts/agent-evals.sh --fast
scripts/agent-evals.sh --integration
```

Behavior evals are separate from validation. They invoke `claude -p`, can consume model tokens, and may be sensitive to model or harness changes. By default, the eval runner exits 0 with a `SKIP` message when the Claude CLI is not installed.

Do not add these evals to CI unless the repo owner explicitly accepts the cost and flakiness tradeoff.

Included fast evals:

- `verify-before-claim.sh`: rejects completion claims without fresh verification evidence.
- `root-cause-first.sh`: starts bugfix work with root-cause investigation.
- `no-invented-gates.sh`: refuses to invent conventional test commands when gates are not configured.

Included integration evals:

- `no-unrelated-changes.sh`: verifies the agent edits only the requested bug file when offered tempting cleanup.
- `bootstrap-pending-completion.sh`: verifies script-first bootstrap can be completed by the agent and pass generated validation.

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
- Optional skills: omitted unless requested and supported; if present, they match `core/skills/README.md`.
- Optional worktree workflow: omitted unless requested; if present, it states opt-in triggers, baseline gate, and cleanup rules.
- GitHub PR template: present only for GitHub-hosted repos and includes problem/evidence/gates/human-review sections.
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
