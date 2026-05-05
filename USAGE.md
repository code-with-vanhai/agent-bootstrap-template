# Usage Guide

This guide explains how to use `agent-bootstrap-template` to add a tool-agnostic agent system to an existing repository.

## Goal

The generated target repo should have these baseline files:

```text
.agent/                  # canonical agent instructions
.agent/roles/prompts/    # prompt fragments for delegated agent work
scripts/agent-eval.sh    # repo-specific verification gates
scripts/agent-gate-discover.sh # evidence-backed candidate gate discovery
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

Claude Code plugin output is optional. The plugin lives in this template repo and provides a first-run wrapper around the same deterministic bootstrap script.

Command prompts are generated for `standard` and `full` feature levels. Claude Code uses them as native slash commands from the plugin; other harnesses use them through the prompt convention documented in generated adapters.

Worktree workflow output is optional. Generate it only when the user opts into worktree-based isolation.

GitHub PR template output is conditional. Generate `.github/PULL_REQUEST_TEMPLATE.md` only for repos confirmed to be GitHub-hosted.

SessionStart hook output is optional. Install hook files only when the user explicitly requests harness-level context injection and the target harness supports it.

MCP discovery output is optional and off by default. Run `scripts/bootstrap-request.sh --with-mcp-discovery ...` only when the user explicitly accepts the advisory MCP layer. With the flag, the bootstrap renders `.mcp.json.suggested` (never an active `.mcp.json`), the `mcp-discover` command, and adds `mcp-discovery-suggested` to `features_enabled`. The flag requires `--features standard` or `--features full`; pairing it with `--features minimal` is rejected at arg validation time. The default bootstrap generates no MCP files. See `core/mcp/README.md`.

## Research Reference

This workflow is based on a practical adaptation of:

- "Autonomous Evolution of EDA Tools: Multi-Agent Self-Evolved ABC", arXiv:2604.15082.
- PDF: https://arxiv.org/pdf/2604.15082
- Local notes: `core/research-basis.md`

The paper uses specialized agents, repository profiling, correctness checks, QoR evaluation, and a self-evolving rulebase to improve a large EDA codebase. This template keeps the useful engineering pattern but applies it conservatively: agents prepare scoped patches, run repo-specific gates, and keep rule changes explicit and reviewable.

## Recommended Workflow

1. Put this template next to the target repository.
2. Use the Claude Code plugin or run `scripts/bootstrap-request.sh` from this template against the target repo.
3. Ask your LLM coding tool to complete `.agent/bootstrap-pending.md` if the script created it.
4. Run validation in the target repo.
5. Review the generated diff before committing.

## Claude Code Plugin Setup

Use this when you want the shortest first-run prompt in Claude Code.

Development or one-session load:

```bash
cd /path/to/target-repo
claude --plugin-dir /path/to/agent-bootstrap-template
```

Reusable local install:

```text
/plugin marketplace add /path/to/agent-bootstrap-template
/plugin install agent-bootstrap@agent-bootstrap-template
```

Then, from Claude Code in the target repository:

```text
/agent-bootstrap:bootstrap
```

You can pass bootstrap flags after the command when needed:

```text
/agent-bootstrap:bootstrap --features full
```

The plugin exposes:

- `core/skills/` as namespaced Claude Code skills.
- `/agent-bootstrap:bootstrap`, `/agent-bootstrap:plan`, `/agent-bootstrap:bugfix`, `/agent-bootstrap:implement`, `/agent-bootstrap:refactor`, `/agent-bootstrap:review`, `/agent-bootstrap:security-review`, `/agent-bootstrap:verify`, and `/agent-bootstrap:release-check` as explicit native slash commands.
- `bin/agent-bootstrap` as a wrapper around `scripts/bootstrap-request.sh` with default `--harness claude`.

The plugin does not install SessionStart hooks automatically and does not replace `.agent/` as the repository source of truth.

## Script-First Setup

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
- `standard`: `minimal` plus `.agent/commands/` and GitHub PR template when the repo is confirmed GitHub-hosted.
- `full`: `standard` plus supported native skills and the optional worktree workflow.

Harness options:

- `generic`: `AGENTS.md`
- `codex`: `AGENTS.md`; with `full`, behavior skills and command-wrapper skills go to `.agents/skills/agent-bootstrap/`
- `claude`: `AGENTS.md` and `CLAUDE.md`; with `full`, skills go to `.claude/skills/agent-bootstrap/`
- `cursor`: `AGENTS.md` and `.cursor/rules/agent-system.mdc`
- `copilot`: `AGENTS.md` and `.github/copilot-instructions.md`
- `gemini`: `AGENTS.md` and `GEMINI.md`

Hooks are never installed by feature level alone. Use `--install-hook` only after confirming the target harness supports the SessionStart hook shape.

MCP discovery is never enabled by feature level alone. Use `--with-mcp-discovery` only when the user explicitly accepts the advisory MCP layer, and only with `--features standard` or `--features full` (the flag is rejected with `minimal`). The flag renders `.mcp.json.suggested` and the `mcp-discover` command but never writes an active `.mcp.json`. Lint any `.mcp.json*` file with `python3 scripts/lib/validate_mcp_config.py` before promoting it.

Claude permission note: command `allowed-tools` frontmatter is a narrow pre-approval hint, not a complete read-only enforcement layer. If a repo needs strict review-only sessions, add Claude Code `permissions.deny` rules or run with `--disallowedTools` for write-capable tools such as `Edit`, `Write`, and unsafe `Bash` patterns.

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
- Create scripts/agent-gate-discover.sh for candidate gate discovery.
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
│   ├── commands/
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
│   ├── agent-gate-discover.sh
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

Candidate gate discovery is available after script-first bootstrap:

```bash
bash scripts/agent-gate-discover.sh --write-suggestions
```

This writes `.agent/gate-suggestions.json` only when `.agent/` already exists.
The suggestions are evidence-backed candidates from checked-in package, build,
task, and CI files. They are not configured gates until reviewed and copied into
both `.agent/gates.md` and `scripts/agent-eval.sh`.

Optional generated files:

```text
.agent/bootstrap-pending.md                # created by bootstrap-request.sh until agent completion
.agent/commands/<command>.md               # generated for standard/full
.agent/workflows/worktree-workflow.md       # only when worktree isolation is requested
.github/PULL_REQUEST_TEMPLATE.md            # only for GitHub-hosted repos
harness-specific SessionStart hook path      # only when explicitly requested
```

## Operating Rules For Generated Repos

Agents using a generated repo should follow these rules:

- Re-read `.agent/rulebase.md` at the start of any coding task.
- Use `.agent/project-profile.md` for repo facts and `.agent/gates.md` for gate commands.
- For Codex, Cursor, Copilot, Gemini, and generic agents, when the user message starts with `agent:<name>`, read `.agent/commands/<name>.md` and treat the remaining text as the task description or gate mode.
- Codex does not need a separate `CODEX.md` adapter in this template because it reads `AGENTS.md`. The template does not generate repo-local `.codex/prompts`; Codex custom prompt files are user-level and not a good fit for repository-scoped bootstrap behavior. Use `agent:<name>` or, with `--harness codex --features full`, invoke the generated `agent-<name>` skills that point back to `.agent/commands/<name>.md`.
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
- Command prompts are validated when `.agent/commands/` exists or manifest `features_enabled` includes `commands`.
- Behavior-shaping guardrails exist in `.agent/rulebase.md` and `.agent/gates.md`.
- No `{{PLACEHOLDER}}` tokens remain.
- `.agent/manifest.json` is valid JSON.
- `scripts/agent-eval.sh` has valid shell syntax.
- `scripts/agent-gate-discover.sh` and its Python helper are present.
- Generated adapters point to `.agent/`.
- Optional GitHub PR template and worktree workflow are validated only when present.

The same script also supports template-source validation. When run from this repository root, it validates source files such as `core/skills/`, `core/github/PULL_REQUEST_TEMPLATE.md`, and `core/workflows/worktree-workflow.md`.

For tooling, call the structured validator directly:

```bash
python3 scripts/lib/validate_agent_system.py --mode auto --format json
python3 scripts/lib/validate_agent_system.py --mode generated --format github
```

`scripts/agent-validate.sh` remains the compatibility wrapper and preserves
`AGENT_ROOT` for validating a generated repo from another working directory.

Then run a configured gate when appropriate:

```bash
bash scripts/agent-eval.sh fast
```

If a gate is marked `not configured`, do not treat that as a failure by itself. Review whether the LLM correctly scanned the repo and documented why no command exists.

To get evidence-backed candidate commands without editing configured gates:

```bash
bash scripts/agent-gate-discover.sh --write-suggestions
```

Review `.agent/gate-suggestions.json`; do not treat candidates as configured
until `.agent/gates.md` and `scripts/agent-eval.sh` have both been updated.

## CI

The template source repository includes `.github/workflows/ci.yml`, which runs
only deterministic checks: shell syntax, `scripts/agent-validate.sh`, Python
unit tests, provider helper tests, `scripts/agent-evals.sh --fast`, and migration
fixtures. It uses `ubuntu-latest` with Python 3.11 and does not require LLM
credentials.

Generated repositories can copy `core/github/agent-template-ci.example.yml` to
`.github/workflows/agent-system.yml`. That workflow validates generated agent
files and runs `scripts/agent-eval.sh fast` when configured. Exit code `2` from
the fast gate is treated as "not configured" so a freshly bootstrapped repo does
not fail CI solely because no real gate has been promoted yet.

## Testing Agent Behavior

This template also includes optional behavior evals for the template itself. Both Claude Code and Codex CLI are supported as of 0.5.0; pick a provider with `--provider` or `AGENT_LLM_PROVIDER` (default `claude`):

```bash
scripts/agent-evals.sh --fast                     # default (claude); deterministic, token-free
scripts/agent-evals.sh --fast --provider codex    # codex variant
scripts/agent-evals.sh --fast --artifact-dir /tmp/agent-eval-artifacts
scripts/agent-evals.sh --integration              # all evals (heaviest; consumes provider quota)
```

Behavior evals are separate from validation. They invoke a headless LLM CLI (`claude -p` or `codex exec`), can consume model tokens, and may be sensitive to model or harness changes. By default, the eval runner exits 0 with a `SKIP` message when the active provider's CLI is not installed or quota/auth-blocked.

Use `--artifact-dir <path>` or `EVAL_ARTIFACT_DIR=<path>` to keep per-eval
metadata and output for debugging. `--artifact-dir` takes precedence over the
environment variable. Be careful uploading artifacts from behavior evals because
they can contain model output.

If your CLI requires extra args in headless mode, pass them through the per-provider env var:

```bash
CLAUDE_EXTRA_ARGS="--allowedTools Bash,Read,Edit,Write" scripts/agent-evals.sh --integration
CODEX_EXTRA_ARGS="--sandbox read-only" scripts/agent-evals.sh --behavior --provider codex
```

Do not add these evals to CI unless the repo owner explicitly accepts the cost and flakiness tradeoff.

See `tests/evals/README.md` for the authoritative provider matrix, the full eval list, and the SKIP/FAIL classifier.

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
- Commands: if generated, `.agent/commands/` includes bootstrap, plan, bugfix, implement, refactor, review, security-review, verify, and release-check prompts.
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

## Syncing Existing Repos

For repos that were already bootstrapped from this template, use the sync runner from the template repo. Dry-run is the default:

```bash
/path/to/agent-bootstrap-template/scripts/agent-sync.sh \
  --target /path/to/target-repo \
  --to 0.3.0
```

Apply only after reviewing the planned changes:

```bash
/path/to/agent-bootstrap-template/scripts/agent-sync.sh \
  --target /path/to/target-repo \
  --to 0.3.0 \
  --apply
```

The runner refuses conflicts by default and performs no content writes when a conflict is detected. If a target file conflict is reviewed and the template version should win, accept that single path explicitly:

```bash
/path/to/agent-bootstrap-template/scripts/agent-sync.sh \
  --target /path/to/target-repo \
  --to 0.3.0 \
  --apply \
  --accept-theirs .agent/commands/verify.md
```

Sync metadata is written to `.agent/manifest.json`, and successful applies append `.agent/sync-log.md`. Adapter files such as `AGENTS.md` and `CLAUDE.md` are not overwritten by default.

### Multi-hop sync (auto and explicit `--multi-hop`)

When the target is several minor releases behind, the runner walks a deterministic chain of single-hop migrations rather than requiring you to run each `--to` manually.

Auto-fallback (default): plain single-hop usage now switches to multi-hop on its own when no direct `current → --to` migration exists. A short notice prints (`Auto-walking multi-hop chain ...`) and the rest of the run is identical to an explicit `--multi-hop`. Pass `--no-auto-multi-hop` to opt out and force the legacy "no migration found" error. Omitting `--to` is still allowed; the runner picks the highest reachable target.

Explicit form is unchanged for users who prefer to be deliberate:

```bash
/path/to/agent-bootstrap-template/scripts/agent-sync.sh \
  --multi-hop \
  --target /path/to/target-repo \
  --to 0.11.0
```

Behavior:

- The runner refuses to touch the target until preflight passes (existence, git, dirty, manifest, current version).
- Without `--apply`, the chain runs end-to-end on a temporary copy of the target (under `$TMPDIR`); the target stays byte-identical.
- With `--apply`, the chain rehearses on the temp copy first; only after every hop succeeds does the runner apply the union of changed files to the real target and append a single aggregated entry to `.agent/sync-log.md`.
- A mid-chain conflict aborts before any write to the target. Pass `--accept-theirs <path>` (repeatable) to clear known conflicts; the flag propagates to every hop in the chain.
- A migration may declare `block_auto_walk_through: true` (see `core/migrations/README.md`) to force users to stop at that intermediate version. The walker raises `NoPathError` rather than silently traversing such hops; run `--to <blocking-version>` first, then continue.
- `--verify-fast` runs the target's `scripts/agent-eval.sh fast` once after the final batch is applied, mirroring single-hop behavior.

Single-hop usage (without `--multi-hop`) shares the same preflight, conflict, and apply semantics; the only difference is that auto-fallback may transparently promote it to a multi-hop run.

### Pre-flight summary, opt-in backups, and known-conflicts catalog

`agent-sync.sh` supports a few opt-in UX flags (see `CHANGELOG.md` **Unreleased** until the next tagged release; scheduled for **0.12.0**):

- `--verbose` (or stdout being a TTY) prints a `Pre-flight summary` block before each apply / dry-run. The block lists the version walk, customization count, and the **post-planner** count of writes / patches / orphans, so you can confirm scope before continuing. CI logs stay short because the block is suppressed when stdout is non-TTY and `--verbose` is unset.
- `--backup` (default off) snapshots every touched file plus `.agent/manifest.json` into your XDG cache (`$XDG_CACHE_HOME/agent-bootstrap/backups`, fallback `~/.cache/...`). The target repo's `.gitignore` is never modified. `scripts/agent-sync.sh backups list` / `restore <backup-id>` / `prune --keep <N>` manage retention. Restoration appends a new audit entry to `.agent/sync-log.md` and never rewrites existing entries.
- A migration's `known_conflicts` catalog (see `core/migrations/README.md`) auto-accepts the template-side write only when the local file's SHA-256 matches one of the recorded `baseline_sha256` values. Customized files still raise a conflict and require `--accept-theirs <path>` — there is no blanket auto-accept.
- The accepted-changes section of `.agent/sync-log.md` is rendered in the D-12 format `- <path> [reason=<reason>, source=<source>]`. Older entries in the legacy bare-path format remain valid; the parser accepts both.

### `doctor` (read-only diagnostics)

Inspect a downstream repo without applying migrations:

```bash
/path/to/agent-bootstrap-template/scripts/agent-sync.sh doctor \
  --target /path/to/target-repo
```

Add `--json` for machine-readable output. The report includes the manifest version, hops remaining to the latest migratable template version, managed-file states vs. your current template version, and orphans. If the newest migration is a no-op (empty `safe_overwrite` / `patches`), the scan falls back to the latest migration that still lists file work so the output stays useful.

### Maintainer version bump (`bump-version.sh`)

`scripts/bump-version.sh <semver>` updates the five public version sources and appends a semver-sorted row to `core/release-tags.md` with commit `<PENDING>`. After `git tag -a`, replace `<PENDING>` with the tag's SHA and run `python3 scripts/lib/check_version_consistency.py --strict` (CI enforces this). See `core/release-process.md`.

## Upgrade Policy

When this template changes:

1. Read `CHANGELOG.md`.
2. If a migration exists, run `scripts/agent-sync.sh` in dry-run mode against the target repo.
3. Apply the migration only after reviewing planned changes and conflicts.
4. Run:

```bash
bash scripts/agent-validate.sh
```

5. Review the final diff manually before committing in the target repo.

## Example

See:

```text
examples/nodejs-sample/
```

This sample shows a filled `.agent/` directory, multiple thin adapters, configured Node.js gates, not-configured gates, and a passing validation script.
