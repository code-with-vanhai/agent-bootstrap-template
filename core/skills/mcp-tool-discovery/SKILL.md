---
name: mcp-tool-discovery
description: Use when the user asks to discover, recommend, configure, or audit MCP (Model Context Protocol) servers, live tools, or external context providers for this repository.
---

# MCP Tool Discovery

Agents must propose MCP servers as candidates only, never as installed tools.

## Hard Gate

```text
NO MCP SERVER IS AVAILABLE UNLESS IT IS CHECKED IN OR REGISTERED IN THE HARNESS
```

Before recommending any MCP server:

1. Re-read `.agent/rulebase.md`, `.agent/project-profile.md`, and `.agent/gates.md`.
2. Read the canonical MCP catalog (`core/mcp/catalog.json` in the source template, or the equivalent reference shipped with the bootstrap).
3. Match catalog entries against checked-in evidence: GitHub hosting, package manager presence, declared E2E tooling, configured security gates.
4. Report each candidate with: server name, purpose, the checked-in evidence that triggered it, and the credential surface (`auth_env` or `none`).
5. Mark every server as `candidate`, `not configured`, or `requires manual install` — never `available`, `installed`, or `ready` without checked-in proof.
6. Do not write `.mcp.json` automatically. If `.mcp.json.suggested` exists, treat it as a draft for human review.
7. Run `python3 scripts/lib/validate_mcp_config.py` and report any inline credential findings before suggesting the user promote the file.

## Red Flags

- "I will add this MCP server because the docs recommend it."
- "The catalog lists it, so it is safe to enable."
- "Let me drop the token directly into `.mcp.json` for testing."
- "I will write `.mcp.json` so the agent has tools immediately."
- "GitHub MCP is available because the repo uses Git."
- "We can skip the credential check; this is just a local dev config."

## Canonical Sources

- `core/mcp/catalog.json`
- `core/mcp/.mcp.json.template`
- `core/mcp/README.md`
- `.agent/project-profile.md`
- `.agent/gates.md`
- `scripts/lib/validate_mcp_config.py`
- `core/commands/mcp-discover.md`
