---
name: bootstrap-agent-system
description: Use when asked to set up, install, instantiate, bootstrap, or configure Agent Bootstrap Kit or an agent system for a repository.
---

# Bootstrap Agent System

Bootstrap must start from the deterministic skeleton, not hand-created files.

## Hard Gate

```text
NO BOOTSTRAP WITHOUT bootstrap-request.sh OR .agent/bootstrap-pending.md
```

If `.agent/bootstrap-pending.md` exists:

1. Read it first.
2. Complete only the listed pending tasks.
3. Scan checked-in repo files before filling repo facts.
4. Configure gates only from checked-in package/build/task/CI evidence.
5. Run `bash scripts/agent-validate.sh`.
6. Delete `.agent/bootstrap-pending.md` only after bootstrap is complete.

If `.agent/bootstrap-pending.md` does not exist:

1. Do not create the `.agent/` skeleton manually.
2. If the Claude Code plugin is installed and `agent-bootstrap` is available, run it from the target repository:

```bash
agent-bootstrap --features standard --target .
```

3. If `agent-bootstrap` is not available, locate `scripts/bootstrap-request.sh` in the installed template or ask the user for the template path.
4. Run or instruct the user to run:

```bash
/path/to/agent-bootstrap-template/scripts/bootstrap-request.sh --features standard --harness <harness> --target .
```

5. After the script creates `.agent/bootstrap-pending.md`, complete the pending tasks.

## Red Flags

- "I can just create the `.agent/` files manually."
- "The user asked for bootstrap, so I can skip the script."
- "I can infer package manager, gates, or framework from conventions."
- "The pending file is just informational."
- "Validation can wait until later."

## Canonical Sources

- `.agent/bootstrap-pending.md`
- `.agent/project-profile.md`
- `.agent/gates.md`
- `.agent/ownership.md`
- `.agent/manifest.json`
- `bin/agent-bootstrap`
- `scripts/bootstrap-request.sh`
- `.claude-plugin/plugin.json`
- `core/bootstrap-steps.md` in the source template
