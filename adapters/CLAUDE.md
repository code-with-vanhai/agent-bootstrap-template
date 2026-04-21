# Claude Code Instructions

This repository uses `.agent/` as the canonical agent instruction source.

For any coding task, MUST re-read `.agent/rulebase.md` before planning or editing, even if it was read earlier in the session.

Read these files before editing:

- `.agent/project-profile.md`
- `.agent/rulebase.md`
- `.agent/ownership.md`
- `.agent/gates.md`
- `.agent/roles/`
- `.agent/workflows/`
- `.agent/decisions.md`
- `.agent/lessons.md`

Run verification through `scripts/agent-eval.sh`.

Keep this file as a thin adapter. Do not duplicate rules here.
