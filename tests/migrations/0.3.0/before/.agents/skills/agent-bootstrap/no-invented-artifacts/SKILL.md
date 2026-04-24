---
name: no-invented-artifacts
description: Use when referencing, configuring, running, or reporting files, commands, gates, APIs, schemas, functions, frameworks, dependencies, or repo facts.
---

# No Invented Artifacts

Agents must verify artifacts before relying on them.

## Hard Gate

```text
NO INVENTED COMMANDS, FILES, FUNCTIONS, GATES, OR REPO FACTS
```

Before referencing an artifact as real:

1. Check the repository or command output.
2. Use exact names and paths from evidence.
3. Mark unknown facts as `not confirmed`.
4. Mark unavailable gates as `not configured` and say where you looked.

## Red Flags

- "This stack usually has npm test."
- "There is probably a CI workflow."
- "The API should be in src/api."
- "I can mention the migration command from convention."
- "The file name is obvious."

## Canonical Sources

- `.agent/project-profile.md`
- `.agent/rulebase.md`
- `.agent/gates.md`
- `scripts/agent-eval.sh`
