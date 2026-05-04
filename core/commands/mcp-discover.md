---
name: mcp-discover
description: Propose candidate MCP servers for this repository from the catalog and checked-in evidence. Report only; do not write `.mcp.json`.
allowed-tools: Read, Grep, Glob, Bash
---

# /agent-bootstrap:mcp-discover

Use this command when the user asks "which MCP servers should we set up here?" or similar.

This command is **report-only**. It does not register, install, or invoke any MCP server. It does not write `.mcp.json`. It may reference `.mcp.json.suggested` if the bootstrap was run with `--with-mcp-discovery`.

## Inputs

- `.agent/project-profile.md` — repository facts: stack, public surface, dangerous operations.
- `.agent/gates.md` — configured gates and their `not configured` markers.
- Checked-in package files: `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `pom.xml`, lockfiles, etc.
- The MCP catalog. In a generated repo, read it from the source template at `core/mcp/catalog.json` (or the path shipped under the agent-bootstrap-template you bootstrapped from). Do not invent catalog entries that are not in the file.
- `.mcp.json.suggested` (if it exists) — a draft client config awaiting human review.

## Workflow

1. Re-read `.agent/rulebase.md` and the canonical sources above before producing any output.
2. For each catalog entry, evaluate `applies_when` against checked-in evidence:
   - `github-hosted` — confirmed by `.github/`, GitHub remote, or `.agent/project-profile.md`.
   - `package-manager-present` — confirmed by a lockfile or manifest.
   - `playwright-dependency-present` — confirmed by `playwright` in `package.json` dependencies or a `playwright.config.*` file.
   - `security-gate-not-configured` — confirmed by `.agent/gates.md` reporting the security gate as `not configured` and `scripts/agent-eval.sh security` exiting 2.
3. Produce a Markdown report with one row per catalog server:
   - `server` — name from the catalog.
   - `purpose` — copied from the catalog.
   - `evidence` — checked-in path that triggered the candidate, or `none`.
   - `credential surface` — the catalog `auth_env` value, or `none`.
   - `recommendation` — one of `candidate`, `not applicable`, `requires manual install`. Never `available` or `installed`.
4. If `.mcp.json.suggested` is present, run `python3 scripts/lib/validate_mcp_config.py` and append its output to the report. Do not promote the file.
5. End the report with the line: `Run scripts/lib/validate_mcp_config.py before promoting any suggested config.`

## Hard Rules

- Do not write `.mcp.json`.
- Do not edit `.mcp.json.suggested` to add real credentials.
- Do not assume an MCP server is installed unless the harness has registered it.
- Do not invoke MCP servers from this command.
- If the catalog cannot be located, report `catalog not found; nothing to recommend` and exit. Do not fabricate candidates.

## When NOT To Use

- If the user wants to actually install an MCP server, point them to their harness documentation. This command is discovery-only.
- If the user wants to edit `.mcp.json` directly, route them through code review and `scripts/lib/validate_mcp_config.py`. Do not auto-edit.
