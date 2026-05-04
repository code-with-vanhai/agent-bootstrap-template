# MCP Layer (Opt In)

This directory describes the candidate set of [Model Context Protocol](https://modelcontextprotocol.io) servers the Agent Bootstrap Kit knows about. It is purely advisory.

The MCP layer is opt-in. By default, `scripts/bootstrap-request.sh` does not generate any MCP files into the target repository. Add `--with-mcp-discovery` only after reading this README.

## What this directory is

- `catalog.json` — versioned registry of candidate MCP servers, their purpose, the situations in which they typically apply, and the environment variable name (if any) used for credentials. The catalog implies nothing about installation, trust, or availability.
- `.mcp.json.template` — a safe example MCP client configuration. Credential fields reference environment variables only; they never contain inline secrets. When `--with-mcp-discovery` is enabled, the bootstrap renders this file as `.mcp.json.suggested` (not `.mcp.json`) so the agent and the human reviewer can examine it before any tool starts using it.
- The `mcp-tool-discovery` skill (`core/skills/mcp-tool-discovery/SKILL.md`) and the `mcp-discover` command (`core/commands/mcp-discover.md`) describe how an agent should propose candidates, citing checked-in evidence such as `.agent/project-profile.md`, `.agent/gates.md`, and dependency manifests.

## Hard rules

- A server in `catalog.json` is a candidate, not an installed tool. Do not claim a server is "available", "configured", or "ready" until the user has installed it and registered it in their harness.
- Never write `.mcp.json` automatically. Only `.mcp.json.suggested` is generated, and only when the user opts in with `--with-mcp-discovery`.
- Never embed real tokens or credentials in `.mcp.json` or `.mcp.json.suggested`. Use environment variable references such as `${GITHUB_TOKEN}` (balanced braces or no braces; mixed forms like `${GITHUB_TOKEN` are rejected). The `scripts/lib/validate_mcp_config.py` linter rejects obvious inline credentials, malformed placeholders, and high-entropy literals — including those hidden behind `Authorization: Bearer …`, `Basic …`, or `Token …` prefixes.
- `--with-mcp-discovery` requires `--features standard` or `--features full`. Combining it with `--features minimal` is rejected at arg validation time, since `minimal` does not generate the `.agent/commands/` surface that the MCP layer points to.
- Treat the MCP layer as additive context. Repository instruction remains canonical in `.agent/`.

## When to use the discovery flow

Reach for `--with-mcp-discovery` only when:

- A teammate or workflow specifically requests live tool discovery.
- The repository already documents an MCP-friendly use case (PR review automation, secret scanning fallback, dependency doc lookup, browser-based E2E).
- The user is willing to review `.mcp.json.suggested` and promote it to `.mcp.json` manually.

If none of those apply, leave the flag off. The default bootstrap remains MCP-free.

## Validation

Run the validator from a generated repo (or this template) to lint any present MCP configuration:

```bash
python3 scripts/lib/validate_mcp_config.py
```

The validator:

- Returns success when no `.mcp.json` and no `.mcp.json.suggested` exist.
- Lints both files when present.
- Rejects obvious inline tokens (`sk-…`, `ghp_…`, `github_pat_…`, `xoxb-…`, `xoxp-…`) and high-entropy literals used as auth values, including those hidden behind `Authorization: Bearer …`, `Basic …`, or `Token …` prefixes.
- Requires credential references to use environment variable names with balanced braces (`${VAR}`) or no braces (`$VAR`). Mixed forms like `${VAR` or `$VAR}` are rejected.

The catalog itself is also checked: `schema_version` must equal `1`, `servers` must be a non-empty object, and each server must declare `purpose`, `applies_when`, and `auth_env`. When `auth_env` is non-null it must be a POSIX-style environment variable name matching `^[A-Z_][A-Z0-9_]*$` (e.g. `GITHUB_TOKEN`, not `${GITHUB_TOKEN}` or `lower-case`); `null` is allowed when no credential is required.

## Out of scope for Stage 5

- Automatic installation, registration, or invocation of any MCP server.
- Live network calls or live MCP server pings during validation or CI.
- A migration that rewrites existing `.mcp.json` files in downstream repos.

The catalog and templates are designed so they can be revisited in a later stage without breaking generated repos that opt in early.
