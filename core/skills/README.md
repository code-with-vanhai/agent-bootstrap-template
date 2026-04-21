# Optional Skills Layer

These skills are optional behavior-shaping artifacts generated only for harnesses with native skill support.

The canonical project governance remains `.agent/`. Skills should stay short and focused on triggers, hard gates, and red flags. Longer process details belong in roles and workflows.

## Skill Mapping

| Skill | Generated path | Canonical source to keep aligned |
|---|---|---|
| `verify-before-completion` | `.agents/skills/agent-bootstrap/verify-before-completion/SKILL.md` or `.claude/skills/agent-bootstrap/verify-before-completion/SKILL.md` | `.agent/gates.md`, `.agent/roles/gate-runner.md` |
| `root-cause-debugging` | `.agents/skills/agent-bootstrap/root-cause-debugging/SKILL.md` or `.claude/skills/agent-bootstrap/root-cause-debugging/SKILL.md` | `.agent/workflows/bugfix-workflow.md`, `.agent/rulebase.md` |
| `scoped-implementation` | `.agents/skills/agent-bootstrap/scoped-implementation/SKILL.md` or `.claude/skills/agent-bootstrap/scoped-implementation/SKILL.md` | `.agent/ownership.md`, `.agent/roles/implementer.md`, `.agent/rulebase.md` |
| `plan-before-code` | `.agents/skills/agent-bootstrap/plan-before-code/SKILL.md` or `.claude/skills/agent-bootstrap/plan-before-code/SKILL.md` | `.agent/roles/planner.md`, `.agent/runs/` convention |
| `worktree-isolation` | `.agents/skills/agent-bootstrap/worktree-isolation/SKILL.md` or `.claude/skills/agent-bootstrap/worktree-isolation/SKILL.md` | `.agent/workflows/worktree-workflow.md` when enabled |
| `no-invented-artifacts` | `.agents/skills/agent-bootstrap/no-invented-artifacts/SKILL.md` or `.claude/skills/agent-bootstrap/no-invented-artifacts/SKILL.md` | `.agent/rulebase.md`, `.agent/gates.md`, `.agent/project-profile.md` |

## Drift Rule

When changing a skill, check the mapped canonical file in the table above in the same review. If the behavior diverges intentionally, document why in `CHANGELOG.md`.
