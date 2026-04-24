# Rule Evolution Workflow

Use this workflow when `.agent/rulebase.md`, `.agent/ownership.md`, `.agent/gates.md`, or role/workflow instructions need to change.

## When To Use

- A repeated agent mistake reveals a missing rule.
- A gate is too broad, too narrow, flaky, or obsolete.
- Ownership boundaries changed with repo architecture.
- A rule blocks beneficial work for reasons no longer valid.
- A new dangerous operation, deploy path, migration path, or public contract is discovered.

## Steps

1. Identify the trigger:
   - incident
   - failed gate
   - review finding
   - architecture change
   - repeated ambiguity
2. Decide whether this is:
   - new rule
   - stricter rule
   - controlled relaxation
   - ownership update
   - gate update
3. Edit the smallest relevant `.agent/` file.
4. If relaxing a rule, document the safety boundary that remains.
5. Add a `lessons.md` entry when the trigger should be remembered.
6. If the change is architectural, add or update `decisions.md`.
7. Review the rule change like code.

## Rule Change Template

```md
Trigger:
- What happened?

Current rule problem:
- Missing | too strict | ambiguous | obsolete

Change:
- Exact rule update.

Safety boundary:
- What remains forbidden or approval-gated?

Applies to:
- Roles, workflows, paths, gates.
```

## Hard Limits

Agents must not silently relax rules for:

- secrets
- production deploys
- remote migrations
- data deletion
- authentication
- authorization
- privacy
- public contracts
- destructive commands

