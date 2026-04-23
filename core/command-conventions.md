# Command Conventions

This file is the canonical documentation for Agent Bootstrap command prompts.

## Canonical Source

- Command prompt files live in `core/commands/*.md`.
- Generated repositories copy them to `.agent/commands/*.md`.
- Claude Code plugin configuration points to `./core/commands/` so native slash commands read the same canonical files.
- Do not keep a second plugin-specific copy of command prompts.

## Drift Rule

Commands must stay thin. They may select a workflow, define invocation input handling, and add mode-specific routing, but long-lived behavior belongs in:

- `.agent/rulebase.md`
- `.agent/gates.md`
- `.agent/workflows/*.md`
- `.agent/roles/*.md`

If a command needs substantial new behavior, create or update a workflow first, then point the command to it.

## Claude Native Slash

Claude Code exposes plugin commands as native slash commands, for example:

```text
/agent-bootstrap:bugfix auth token refresh fails after network error
```

Claude Code supports arguments for invoked skills and commands. Command files should use `$ARGUMENTS` for the native Claude command path and keep explicit fallback wording for prompt-based `agent:<name>` invocations in non-Claude harnesses.

Reference:

- https://code.claude.com/docs/en/slash-commands
- https://docs.claude.com/en/docs/claude-code/plugins-reference

## Prompt-Based Convention

Tools without native plugin slash commands may use this convention:

```text
agent:bugfix auth token refresh fails after network error
```

When a user message starts with `agent:<name>`:

1. Read `.agent/commands/<name>.md`.
2. Treat everything after `agent:<name>` as the task description or mode.
3. Follow the command file exactly.

This is a prompt convention, not a real runtime command system.

For Codex repositories generated with `--features full`, the template also creates thin repository-local skills named `agent-<name>` under `.agents/skills/agent-bootstrap/`. These are wrappers only; `.agent/commands/<name>.md` remains the canonical command prompt.

## Permission Hardening

Claude command `allowed-tools` frontmatter should be treated as a narrow pre-approval hint, not as the only read-only enforcement layer. For strict read-only review sessions, use Claude Code permission deny rules or CLI `--disallowedTools` to block write-capable tools such as `Edit`, `Write`, and unsafe `Bash` patterns.

Example project policy for strict review environments:

```json
{
  "permissions": {
    "deny": [
      "Edit",
      "Write",
      "Bash(git push:*)",
      "Bash(git tag:*)",
      "Bash(rm:*)"
    ]
  }
}
```

## Adapter Policy

Add the prompt-based convention to adapters for tools that do not have Agent Bootstrap native slash support:

- `adapters/AGENTS.md`
- `adapters/copilot-instructions.md`
- `adapters/cursor-agent-system.mdc`
- `adapters/GEMINI.md`

Do not add the prompt-based convention to `adapters/CLAUDE.md`; Claude users should use native `/agent-bootstrap:<name>` commands.

## Existing Repo Migration

For a repository already bootstrapped before commands existed:

1. Copy `core/commands/*.md` to `.agent/commands/*.md`.
2. Copy `core/workflows/release-check-workflow.md` to `.agent/workflows/release-check-workflow.md`.
3. Add the command convention section to `AGENTS.md` after `## Canonical Instructions` and before `## Operating Rules` when those headings exist.
4. Update `.agent/gates.md` to document the `scripts/agent-eval.sh <mode>` signature and the supported gate modes.
5. Add `"commands"` to `.agent/manifest.json` `features_enabled`.
6. Run `bash scripts/agent-validate.sh`.
