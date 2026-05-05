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
- Ten optional native behavior skills: verify-before-completion, root-cause-debugging, scoped-implementation, plan-before-code, worktree-isolation, no-invented-artifacts, bootstrap-agent-system, no-secret-leakage, data-safety, and mcp-tool-discovery.
- Optional worktree workflow for teams that explicitly opt into isolated workspaces.
- Optional GitHub pull request template for GitHub-hosted repositories.
- Optional SessionStart hook template for supported harnesses, off by default.
- Optional MCP discovery layer via `--with-mcp-discovery`, off by default; renders an advisory `.mcp.json.suggested` plus the `mcp-discover` command for human review.
- Deterministic bootstrap skeleton generation via `scripts/bootstrap-request.sh`.
- Optional Claude Code native slash commands through `/agent-bootstrap:bootstrap`, `/agent-bootstrap:plan`, `/agent-bootstrap:bugfix`, `/agent-bootstrap:implement`, `/agent-bootstrap:refactor`, `/agent-bootstrap:review`, `/agent-bootstrap:security-review`, `/agent-bootstrap:verify`, and `/agent-bootstrap:release-check`.
- Prompt-based command convention for non-Claude harnesses through `agent:<name>` when `.agent/commands/` is generated.
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
│   ├── constitution.template.md
│   ├── rulebase.template.md
│   ├── ownership.template.md
│   ├── gates.template.md
│   ├── decisions.template.md
│   ├── lessons.template.md
│   ├── hooks/
│   ├── github/
│   ├── commands/
│   ├── mcp/
│   ├── roles/
│   │   └── prompts/
│   ├── skills/
│   └── workflows/
├── adapters/
├── .claude-plugin/
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

The plugin also exposes native Claude Code slash commands from `core/commands/`:

```text
/agent-bootstrap:plan <task>
/agent-bootstrap:bugfix <bug>
/agent-bootstrap:implement <run-or-task>
/agent-bootstrap:refactor <scope>
/agent-bootstrap:review <scope>
/agent-bootstrap:security-review <scope>
/agent-bootstrap:verify fast
/agent-bootstrap:release-check
```

### Script-First Setup

1. Clone or copy this template near the target repository.
2. From the target repository, generate the deterministic skeleton:

```bash
/path/to/agent-bootstrap-template/scripts/bootstrap-request.sh \
  --features standard \
  --harness claude \
  --target .
```

Use `--harness codex`, `cursor`, `copilot`, `gemini`, or `generic` for other tools. Codex intentionally uses `AGENTS.md` as its adapter; with `--features full`, repository skills are generated under `.agents/skills/agent-bootstrap/`, including thin command-wrapper skills that point back to `.agent/commands/`. Use `--features minimal` for the smallest baseline or `--features full` to also generate supported native skills and the optional worktree workflow.

3. Ask your coding agent:

```text
Complete .agent/bootstrap-pending.md
```

4. In the target repo, run:

```bash
bash scripts/agent-validate.sh
```

5. Optionally run candidate gate discovery:

```bash
bash scripts/agent-gate-discover.sh --write-suggestions
```

Review `.agent/gate-suggestions.json` before promoting any candidate into `.agent/gates.md` and `scripts/agent-eval.sh`.

6. Review the generated `.agent/` files and thin adapters.
7. Commit the generated agent system only after the repo-specific facts, gates, dangerous operations, and ownership boundaries are correct.

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
│   ├── commands/          # Generated for standard/full; prompt convention for non-Claude tools
│   ├── roles/
│   │   └── prompts/
│   ├── runs/              # Created per non-trivial task, not required at bootstrap
│   └── workflows/
├── scripts/
│   ├── agent-eval.sh
│   ├── agent-gate-discover.sh
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
.agent/commands/<command>.md
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

MCP discovery output is optional. The default bootstrap generates no `.mcp.json` and no `.mcp.json.suggested`. Pass `--with-mcp-discovery` only when the user explicitly accepts the advisory MCP layer; the bootstrap then renders `.mcp.json.suggested` (never `.mcp.json`), copies `.agent/commands/mcp-discover.md`, and adds `mcp-discovery-suggested` to `features_enabled`. The flag requires `--features standard` or `--features full`; combining it with `--features minimal` is rejected at arg validation time. See `core/mcp/README.md`.

## Validation And Evals

Run generated-repo validation from the target repo:

```bash
bash scripts/agent-validate.sh
```

Discover candidate gates from checked-in package, build, task, and CI files:

```bash
bash scripts/agent-gate-discover.sh --write-suggestions
```

The output is advisory JSON. Review each `candidate` before editing
`.agent/gates.md` or `scripts/agent-eval.sh`.

Run template-source validation from this repo:

```bash
bash scripts/agent-validate.sh
```

The validator also supports explicit modes and structured output:

```bash
python3 scripts/lib/validate_agent_system.py --mode template --format json
python3 scripts/lib/validate_agent_system.py --mode generated --format github
```

This repository includes a GitHub Actions workflow at `.github/workflows/ci.yml`
that runs the same deterministic checks on `ubuntu-latest` with Python 3.11:
template validation, Python unit tests, provider helper tests, deterministic
fast evals, and migration fixtures. It does not run LLM-driven behavior evals or
require provider credentials.

Generated repositories can use `core/github/agent-template-ci.example.yml` as a
starting point. The example validates generated agent files and treats
`scripts/agent-eval.sh fast` exit code `2` as "not configured" rather than a
false CI failure.

Run optional headless behavior evals from this repo. Both Claude Code and Codex CLI are supported; pick one with `--provider` or `AGENT_LLM_PROVIDER`. The eval runner exits 0 with `SKIP` when the active provider's CLI is missing or quota/auth-blocked. Evals are intentionally not wired into validation or CI by default.

```bash
scripts/agent-evals.sh --fast                     # default (claude); deterministic, token-free
scripts/agent-evals.sh --fast --provider codex    # codex variant
scripts/agent-evals.sh --fast --artifact-dir /tmp/agent-eval-artifacts
scripts/agent-evals.sh --integration              # all evals (heaviest; consumes quota)
```

See `tests/evals/README.md` for the provider matrix, per-provider env vars (`CLAUDE_BIN`, `CLAUDE_EXTRA_ARGS`, `CODEX_BIN`, `CODEX_EXTRA_ARGS`), the SKIP/FAIL classifier, and the included eval list.

## Upgrade Policy

When this template changes, prefer the migration runner over manual re-instantiation:

1. Read `CHANGELOG.md` and the relevant `core/migrations/<version>/migration.json`.
2. From a clean target worktree, dry-run the sync. Single-hop is the normal entry point and now auto-walks a multi-hop chain when no direct migration exists from your current version:

   ```bash
   /path/to/agent-bootstrap-template/scripts/agent-sync.sh \
     --target /path/to/target-repo \
     --to 0.11.0 \
     --verbose
   ```

   The pre-flight summary lists planned writes, configured patches, orphan files, and whether `--backup` is enabled. Add `--apply` once the dry-run is clean.
3. For a reversible upgrade, pass `--backup` so the runner snapshots every touched file (and `.agent/manifest.json`) into your XDG cache before writing. `scripts/agent-sync.sh backups list / restore <id> / prune` manage those snapshots; restore appends a new entry to `.agent/sync-log.md` rather than rewriting the existing log.
4. After applying, run `scripts/agent-validate.sh` in the target repo and review the diff before committing.

Conflicts still abort the run by default; pass `--accept-theirs <path>` per file when the template version should win. The append-only `.agent/sync-log.md` records each apply and any restore for audit. See [`USAGE.md`](USAGE.md) for the full flag reference and worked examples.
