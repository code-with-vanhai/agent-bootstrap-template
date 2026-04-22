# Agent Bootstrap Template

Tool-agnostic template for adding a repository-local agent operating system to an existing codebase.

The generated project files live under `.agent/` and are the canonical source of truth for all coding assistants. Tool-specific files such as `AGENTS.md`, `CLAUDE.md`, Cursor rules, Gemini instructions, and Copilot instructions should stay thin and point back to `.agent/`.

The current template focuses on four things:

- Repository facts: stack, public surface, ownership, dangerous operations, and configured gates are derived from checked-in files.
- Behavior guardrails: rulebase and gates include hard requirements for verification, root-cause-first debugging, no invented artifacts, and no unrelated changes.
- Delegation structure: roles, prompt fragments, workflows, and optional native skills make common agent behavior explicit.
- Verification: `agent-validate.sh` checks generated file shape and required content; optional headless evals test whether instructions actually shape agent behavior.

## Research Reference

This template is inspired by the repository-scale multi-agent evolution loop described in:

- Cunxi Yu and Haoxing Ren, "Autonomous Evolution of EDA Tools: Multi-Agent Self-Evolved ABC", arXiv:2604.15082.
- PDF: https://arxiv.org/pdf/2604.15082
- Summary of applied lessons: `core/research-basis.md`

The paper shows that agents work best when they are given strong repository knowledge, scoped ownership, correctness checks, measurable evaluation, and a controlled rulebase. This template adapts those ideas for general software repositories with human-in-the-loop operation.

## Design Principles

This template is based on a conservative adaptation of repository-scale multi-agent code evolution:

- Spend effort on repo profiling before code changes.
- Use specialized roles and non-overlapping ownership.
- Require verification gates before accepting changes.
- Keep a champion state and reject regressions.
- Treat the rulebase as evolvable, but only through controlled review.
- Prefer improvements with precedent in the codebase before introducing new architecture.
- Keep generated adapters thin; `.agent/` remains the canonical instruction source.
- Prefer `not configured` over invented gates, commands, files, frameworks, or repo facts.
- Treat worktrees, native skills, hooks, and PR templates as optional layers, not required baseline output.

## Current Capabilities

The template currently provides:

- Core `.agent/` templates for project profile, rulebase, ownership, gates, decisions, lessons, roles, and workflows.
- Four role prompt fragments for planner, implementer, reviewer, and gate-runner subagents.
- Seven optional native behavior skills: verify-before-completion, root-cause-debugging, scoped-implementation, plan-before-code, worktree-isolation, no-invented-artifacts, and bootstrap-agent-system.
- Optional worktree workflow for teams that explicitly opt into isolated workspaces.
- Optional GitHub pull request template for GitHub-hosted repositories.
- Optional SessionStart hook template for supported harnesses, off by default.
- Deterministic bootstrap skeleton generation via `scripts/bootstrap-request.sh`.
- Optional Claude Code plugin wrapper for first-run bootstrap through `/agent-bootstrap:bootstrap`.
- Template and generated-repo validation via `scripts/agent-validate.sh`.
- Optional headless behavior evals via `scripts/agent-evals.sh`.

## Template Layout

```text
agent-bootstrap-template/
├── CHANGELOG.md
├── USAGE.md
├── core/
│   ├── README.md
│   ├── research-basis.md
│   ├── bootstrap-steps.md
│   ├── instantiation-prompt.md
│   ├── bootstrap-checklist.md
│   ├── manifest.template.json
│   ├── project-profile.template.md
│   ├── rulebase.template.md
│   ├── ownership.template.md
│   ├── gates.template.md
│   ├── decisions.template.md
│   ├── lessons.template.md
│   ├── hooks/
│   ├── github/
│   ├── roles/
│   │   └── prompts/
│   ├── skills/
│   └── workflows/
├── adapters/
├── .claude-plugin/
├── commands/
├── bin/
├── examples/
├── scripts/
│   ├── agent-eval.template.sh
│   ├── agent-evals.sh
│   ├── bootstrap-request.sh
│   └── agent-validate.sh
└── tests/
    └── evals/
```

## Quickstart

### Claude Code Plugin

For the lowest-friction Claude Code setup, load or install this repo as a plugin, then run the plugin command from the target repository:

```bash
cd /path/to/target-repo
claude --plugin-dir /path/to/agent-bootstrap-template
```

Inside Claude Code, from the target repo:

```text
/agent-bootstrap:bootstrap
```

For reusable local install, add the local marketplace and install the plugin:

```text
/plugin marketplace add /path/to/agent-bootstrap-template
/plugin install agent-bootstrap@agent-bootstrap-template
```

The plugin exposes `core/skills/` directly, so the `bootstrap-agent-system` skill can trigger from a short request like "Set up agent system here." It still uses `scripts/bootstrap-request.sh`; it does not hand-create `.agent/`.

### Script-First Setup

1. Clone or copy this template near the target repository.
2. From the target repository, generate the deterministic skeleton:

```bash
/path/to/agent-bootstrap-template/scripts/bootstrap-request.sh \
  --features standard \
  --harness claude \
  --target .
```

Use `--harness codex`, `cursor`, `copilot`, `gemini`, or `generic` for other tools. Use `--features minimal` for the smallest baseline or `--features full` to also generate supported native skills and the optional worktree workflow.

3. Ask your coding agent:

```text
Complete .agent/bootstrap-pending.md
```

4. In the target repo, run:

```bash
bash scripts/agent-validate.sh
```

5. Review the generated `.agent/` files and thin adapters.
6. Commit the generated agent system only after the repo-specific facts, gates, dangerous operations, and ownership boundaries are correct.

Manual fallback for harnesses where you want the agent to do the full instantiation:

```text
Setup Agent Bootstrap Kit for this repo.
Read core/instantiation-prompt.md from the agent-bootstrap-template repo and instantiate it here.
Scan the repo first. Do not modify business logic. Do not deploy. Do not run remote migrations.
Mark unknown gates as not configured instead of inventing commands.
Generate optional skills, worktree workflow, and hooks only when supported and requested. Generate the GitHub PR template only when the repo is confirmed GitHub-hosted.
```

For detailed usage, see `USAGE.md`.

## Intended Generated Layout

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
│   ├── runs/              # Created per non-trivial task, not required at bootstrap
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

Optional outputs:

```text
.agent/bootstrap-pending.md
.agents/skills/agent-bootstrap/<skill>/SKILL.md
.claude/skills/agent-bootstrap/<skill>/SKILL.md
.agent/workflows/worktree-workflow.md
.github/PULL_REQUEST_TEMPLATE.md
harness-specific SessionStart hook path
```

## Instantiation Rule

Prefer `scripts/bootstrap-request.sh` for first setup. It copies the deterministic skeleton and writes `.agent/bootstrap-pending.md`; the agent then completes only repo-specific classification, gates, ownership, and manifest fields.

Do not copy placeholders blindly. For each target repo, scan the actual repository and replace template sections with observed facts. If a gate, test framework, deploy command, or ownership boundary is unknown, mark it as `not configured` instead of inventing it.

Native skill output is optional. Generate skills from `core/skills/` only when the target harness supports native skill discovery and the user wants skill files. `.agent/` remains the canonical repository instruction source.

Worktree workflow output is optional. Generate `.agent/workflows/worktree-workflow.md` only when the user opts into worktree-based isolation or the target repo already documents it.

GitHub PR template output is conditional. Generate `.github/PULL_REQUEST_TEMPLATE.md` from `core/github/PULL_REQUEST_TEMPLATE.md` only for repos confirmed to be GitHub-hosted.

SessionStart hook output is optional. Copy `core/hooks/session-start.sh` only when the user explicitly asks for context injection and the target harness supports that hook shape.

## Validation And Evals

Run generated-repo validation from the target repo:

```bash
bash scripts/agent-validate.sh
```

Run template-source validation from this repo:

```bash
bash scripts/agent-validate.sh
```

Run optional headless behavior evals from this repo when the Claude CLI is available and the cost/flakiness tradeoff is acceptable:

```bash
scripts/agent-evals.sh --fast
scripts/agent-evals.sh --integration
```

The eval runner exits 0 with `SKIP` when the Claude CLI is missing. Evals are intentionally not wired into validation or CI by default.

## Upgrade Policy

When this template changes, re-instantiate manually:

1. Read `CHANGELOG.md`.
2. Apply only relevant template changes to the target repo.
3. Review the diff.
4. Run `scripts/agent-validate.sh` in the target repo.

Do not use automatic migrations for agent rules unless a future incident proves they are necessary.
