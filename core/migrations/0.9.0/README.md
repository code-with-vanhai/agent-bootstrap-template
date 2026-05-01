# Migration: 0.8.1 -> 0.9.0

## Source Acceptance

This migration accepts only `0.8.1` as a source version.

Repos on earlier versions can use `scripts/agent-sync.sh --multi-hop --to 0.9.0`
from a template checkout that includes the 0.9.0 migration.

## What This Migration Ships

0.9.0 updates downstream generated repos with:

- append-only audit log support through `scripts/agent-audit-log.sh`, the
  `scripts/agent-eval.sh` EXIT trap, and the `scripts/agent-validate-plan.sh`
  audit wrapper;
- candidate gate marker blocks in `scripts/agent-eval.sh` plus
  `scripts/lib/insert_gate_candidates.py`;
- plan-validator JSON output support;
- generated validator checks for skill-manifest drift, Data Surface coverage,
  audit-log wiring, gate candidate markers, and three-tier thin adapters;
- `## Data Surface` in `.agent/project-profile.md`, inserted additively to
  preserve repo-specific profile content;
- best-effort audit-log notes in subagent prompt fragments;
- the `data-safety` behavior skill when the target already has a supported
  native skill root (`.agents/skills/agent-bootstrap` or
  `.claude/skills/agent-bootstrap`);
- thin-adapter tier headings for adapter files that already exist in the
  target.

The off-by-default PreToolUse secret-guard hook and Claude native subagents are
available to new bootstraps. This migration does not auto-install hooks or
create Claude native subagents in existing repos.

## Conditional File Policy

The migration uses conditional `safe_overwrite` entries for surfaces that may
not exist in every generated target:

- `skip_if_target_missing` updates optional adapters only when that adapter file
  already exists;
- `enabled_when_path_exists` installs the new `data-safety` skill only when the
  corresponding native skill root already exists.

Customized target files still conflict by default. Review the conflict and pass
`--accept-theirs <path>` only when the 0.9.0 template version should replace the
target copy.

## Verification

`tests/migrations/0.9.0/run.sh` builds a genuine 0.8.1 fixture from the
canonical 0.3.0 baseline, applies 0.9.0, asserts the manifest/sync-log update,
checks Data Surface, audit-log wiring, candidate markers, JSON output, adapter
headings, conditional `data-safety` skill installation, generated validation,
and idempotent re-apply.
