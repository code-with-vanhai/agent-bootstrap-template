# Instantiation Prompt

Use this prompt when an LLM instantiates this template into a target repository.

`core/bootstrap-steps.md` is the canonical bootstrap process. This file is the expanded LLM-facing version for agents that are completing bootstrap manually or finishing `.agent/bootstrap-pending.md`.

## Prompt

You are setting up a tool-agnostic agent system for an existing repository.

Your job is to instantiate this template into the target repo by creating `.agent/` as the canonical instruction source, plus thin tool-specific adapters. Do not modify business logic.

Follow `core/bootstrap-steps.md` and this expanded process:

## Step 1: Scan

Inspect the repository before generating files.

Required scan targets:

- Root files: `README*`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.gitignore`.
- Package/build files: `package.json`, `pnpm-workspace.yaml`, `turbo.json`, `pyproject.toml`, `requirements.txt`, `Cargo.toml`, `go.mod`, `pom.xml`, `build.gradle`, `Makefile`, `justfile`, `Taskfile.yml`.
- CI files: `.github/workflows/*`, `.gitlab-ci.yml`, `azure-pipelines.yml`, `Jenkinsfile`.
- Source roots: `src/`, `app/`, `apps/`, `packages/`, `lib/`, `server/`, `client/`, `api/`, `web/`, `backend/`, `frontend/`, `services/`.
- Test roots: `test/`, `tests/`, `e2e/`, `spec/`, `__tests__/`.
- Docs and contracts: `docs/`, `openapi*`, `swagger*`, `schema*`, `migrations/`, `prisma/`, `drizzle/`, `proto/`, `graphql/`.
- Infra/deploy: `Dockerfile`, `docker-compose*`, `terraform/`, `infra/`, `k8s/`, `helm/`, `wrangler.toml`, `vercel.json`, `netlify.toml`.

## Step 2: Classify

Derive facts only from files found in the repo.

Classify:

- Primary language.
- Package manager or build tool.
- Frameworks.
- Runtime and deployment targets.
- Test framework and commands.
- Build/typecheck/lint commands.
- Public surface: APIs, CLI, package exports, routes, schemas, config formats, docs usage.
- Dangerous operations: deploy, remote migration, data deletion, secret/key handling, production scripts.
- Ownership boundaries: at least root-level paths, and per-package boundaries for monorepos when obvious.

Anti-hallucination rules:

- A gate command may be written only if it appears in `package.json`, Makefile/justfile/Taskfile, CI workflow, or an equivalent checked-in build file.
- If no command is found, write `not configured` and explain where you looked.
- Do not invent frameworks, deployment targets, databases, queues, cloud providers, or test tools.
- Do not infer production behavior from names alone; mark uncertain facts as `not confirmed`.

## Step 3: Generate

Create or update these files in the target repo:

```text
.agent/
├── README.md
├── manifest.json
├── project-profile.md
├── rulebase.md
├── ownership.md
├── gates.md
├── decisions.md
├── lessons.md
├── roles/
│   ├── planner.md
│   ├── implementer.md
│   ├── reviewer.md
│   ├── gate-runner.md
│   └── prompts/
│       ├── planner-subagent.md
│       ├── implementer-subagent.md
│       ├── reviewer-subagent.md
│       └── gate-runner-subagent.md
└── workflows/
    ├── bootstrap-workflow.md
    ├── feature-workflow.md
    ├── bugfix-workflow.md
    ├── refactor-workflow.md
    ├── review-workflow.md
    ├── security-review-workflow.md
    ├── improvement-cycle-workflow.md
    └── rule-evolution-workflow.md
```

Create:

```text
scripts/agent-eval.sh
scripts/agent-validate.sh
```

Create thin adapters when appropriate for the user's tools:

```text
AGENTS.md
CLAUDE.md
GEMINI.md
.cursor/rules/agent-system.mdc
.github/copilot-instructions.md
```

Create GitHub metadata when appropriate:

```text
.github/PULL_REQUEST_TEMPLATE.md
```

Default adapter policy:

- If a matching adapter already exists, update it to point to `.agent/` while preserving important existing repo-specific instructions.
- If no adapter exists, create the common adapters unless the user asks for selected tools only.
- Every generated adapter must require agents to re-read `.agent/rulebase.md` at the start of any coding task.
- Do not duplicate the full rulebase inside adapters.
- Do not install hook files unless the user explicitly asks for harness-specific hook integration.

Optional skills policy:

- Skills are optional behavior-shaping artifacts, not a replacement for `.agent/`.
- Generate skills only when the target harness supports native skill discovery and the user wants skill output.
- For Codex-style harnesses, copy `core/skills/*/SKILL.md` to `.agents/skills/agent-bootstrap/<skill>/SKILL.md`.
- For Claude Code project-local skills, copy `core/skills/*/SKILL.md` to `.claude/skills/agent-bootstrap/<skill>/SKILL.md` when that layout is supported by the user's tool setup.
- For Claude Code plugin installs, do not copy plugin files into the target repo; the plugin exposes `core/skills/`, `/agent-bootstrap:bootstrap`, and `bin/agent-bootstrap` from the template repo.
- If the harness does not support skills, skip skill output and keep `.agent/` plus adapters as the source of truth.
- Keep `core/skills/README.md` mapping aligned with every skill file.

Optional worktree workflow policy:

- Worktree workflow is optional acceleration, not a required generated workflow.
- Generate `.agent/workflows/worktree-workflow.md` from `core/workflows/worktree-workflow.md` only when the user explicitly opts in during bootstrap or the target repo already documents worktree usage.
- If not enabled, skip this workflow and note the skip in the final report.
- Do not install automation scripts for creating worktrees in this step.

GitHub metadata policy:

- If the target repo is hosted on GitHub, generate `.github/PULL_REQUEST_TEMPLATE.md` from `core/github/PULL_REQUEST_TEMPLATE.md`.
- Detect GitHub hosting from an existing `.github/` directory or a checked git remote containing `github.com`.
- If the target repo is not GitHub-hosted, skip the PR template and note the skip in the final report.
- Do not generate GitLab, Bitbucket, Gitea, or other merge request templates in this step.

## Source Mapping

Use the template files as the source of truth. Do not recreate these files from memory.

| Template source | Target path | Handling |
|---|---|---|
| `core/README.md` | `.agent/README.md` | Copy and adjust repo-specific wording if needed |
| `core/*.template.md` | `.agent/<name>.md` | Fill placeholders and customize from repo scan |
| `core/roles/*.md` | `.agent/roles/*.md` | Copy and trim only when repo scope justifies it |
| `core/roles/prompts/*.md` | `.agent/roles/prompts/*.md` | Copy prompt fragments; keep harness-agnostic wording |
| `core/workflows/*.md` | `.agent/workflows/*.md` | Copy and trim only when repo scope justifies it |
| `core/workflows/worktree-workflow.md` | `.agent/workflows/worktree-workflow.md` | Optional only; copy when user opts into worktree workflow |
| `core/manifest.template.json` | `.agent/manifest.json` | Fill placeholders; keep valid JSON |
| `scripts/agent-validate.sh` | `scripts/agent-validate.sh` | Copy verbatim unless target repo has path constraints |
| `scripts/agent-eval.template.sh` | `scripts/agent-eval.sh` | Customize commands from checked-in repo evidence |
| `adapters/AGENTS.md` | `AGENTS.md` | Thin adapter; preserve relevant existing instructions |
| `adapters/CLAUDE.md` | `CLAUDE.md` | Thin adapter; preserve relevant existing instructions |
| `adapters/GEMINI.md` | `GEMINI.md` | Thin adapter; preserve relevant existing instructions |
| `adapters/cursor-agent-system.mdc` | `.cursor/rules/agent-system.mdc` | Thin adapter |
| `adapters/copilot-instructions.md` | `.github/copilot-instructions.md` | Thin adapter |
| `core/github/PULL_REQUEST_TEMPLATE.md` | `.github/PULL_REQUEST_TEMPLATE.md` | GitHub-hosted repos only |
| `core/hooks/session-start.sh` | harness-specific hook path | Optional only; copy when the user requests SessionStart context injection |
| `core/skills/*/SKILL.md` | `.agents/skills/agent-bootstrap/<skill>/SKILL.md` or `.claude/skills/agent-bootstrap/<skill>/SKILL.md` | Optional only; copy when the harness supports native skills |
| `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `commands/bootstrap.md`, `bin/agent-bootstrap` | Claude Code plugin install | Optional template-level distribution layer; do not copy into target repos |

If the target harness is Claude Code and the user wants dispatchable agents, adapt `.agent/roles/prompts/*-subagent.md` into `.claude/agents/<role>.md`. Otherwise keep prompt fragments under `.agent/roles/prompts/` for copy/paste or manual delegation.

Do not create `.agent/runs/*` during bootstrap unless there is a real non-trivial follow-up task to plan. Runs are created per task, not as required bootstrap files.

## Step 4: Self-Verify

Before reporting done:

- Complete `core/bootstrap-checklist.md` against the generated repo.
- Run the generated validation script:

```bash
bash scripts/agent-validate.sh
```

- Run `bash -n scripts/agent-eval.sh`.
- Check that no `{{PLACEHOLDER}}` tokens remain in `.agent/`, adapters, or generated scripts.
- Confirm `manifest.json` is valid JSON.
- Confirm generated adapters require re-reading `.agent/rulebase.md` for coding tasks.
- Confirm `.agent/roles/prompts/` contains the four subagent prompt fragments.
- If optional skills were generated, confirm every skill listed in `core/skills/README.md` exists.
- If worktree workflow was requested, confirm `.agent/workflows/worktree-workflow.md` was generated.
- If the repo is GitHub-hosted, confirm `.github/PULL_REQUEST_TEMPLATE.md` was generated from `core/github/PULL_REQUEST_TEMPLATE.md`.
- Confirm optional hooks were not installed unless explicitly requested.

## Output Contract

Report:

- Files generated or updated.
- Detected stack and package manager.
- Configured gates and evidence source for each command.
- Known not-configured gates.
- Dangerous operations found.
- Public surface classified.
- Any adapters created or updated.
- Whether GitHub PR template was generated or skipped.
- Any optional skills or hooks created.
- Whether optional worktree workflow was generated or skipped.
- Validation result.
- Remaining human follow-up.

## Do Not

- Do not change product or business logic.
- Do not deploy.
- Do not run remote migrations.
- Do not edit secrets or env values.
- Do not add dependencies for the app.
- Do not invent gates or repo facts.
