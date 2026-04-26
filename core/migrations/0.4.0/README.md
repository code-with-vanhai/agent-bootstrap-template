# Migration: 0.3.0 / 0.3.2 → 0.4.0

## Source acceptance

This migration accepts both `0.3.0` and `0.3.2` as source versions through a single
`migration.json` using the schema v1 extension `from_versions: ["0.3.0", "0.3.2"]`.
The `0.3.2` release was a metadata-only version drift fix; the rendered `.agent/`
content is byte-identical to `0.3.0`, so a single migration covers both sources.

## What this migration ships

- **New scripts** distributed via `safe_overwrite`:
  - `scripts/agent-validate-plan.sh` — plan discipline command (not a gate mode).
  - `scripts/lib/validate_plan.py` — Python validator with EV/SC/LP/SECT/AC checks.
  - `scripts/lib/__init__.py` — package marker.
- **Updated** `scripts/agent-validate.sh` (placeholder regex hardening + new path checks).
- **Patched** `.agent/` files via idempotent anchor patches:
  - `.agent/rulebase.md` — adds `## Status Field Whitelist`.
  - `.agent/workflows/feature-workflow.md` — adds `## Grounding Requirements`.
  - `.agent/workflows/review-workflow.md` — adds `## Plan/Spec Review`.
  - `.agent/roles/planner.md` — adds Evidence Blocks, Existing Behaviors Preserved,
    AC Verification Method, and Status Discipline sections.
  - `.agent/roles/reviewer.md` — adds Plan/Spec Grounding Pass.
  - `.agent/gates.md` — adds AC Verification Taxonomy and Plan Discipline Command sections.
- **Manifest updates** — bumps `template_version`, `synced_to_template_version`,
  records `synced_to_template_commit`, and appends a release note.

## Native-skills feature

Repos that bootstrapped with the `native-skills` feature have an additional
`.agents/skills/agent-bootstrap/verify-before-completion/SKILL.md`. This
migration does **not** patch that file because the patch system has no
feature gate and the canonical Status Field Whitelist already lives in
`.agent/rulebase.md`. Re-bootstrapping is optional if you want the skill text
itself to mention the whitelist explicitly.

## Idempotency

All patches use `skip_if_contains` markers so re-running `agent-sync.sh --apply`
is a no-op once the migration has succeeded. Re-running with `--target . --to 0.4.0`
on an already-synced repo prints "Target already synced to 0.4.0; no-op."

## Customizations

`safe_overwrite` keeps user/teammate edits intact byte-for-byte (ours==theirs check).
If a target file diverges from both `0.3.x` and `0.4.0` shipped versions, the
migration aborts with a `ConflictError` and lists the conflicting paths. Resolve
manually or re-run with `--accept-theirs <path>` to overwrite.
