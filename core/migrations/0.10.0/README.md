# Migration: 0.9.0 -> 0.10.0

## Source Acceptance

This migration accepts only `0.9.0` as a source version.

Repos on earlier versions can use `scripts/agent-sync.sh --multi-hop --to 0.10.0`
from a template checkout that includes the 0.10.0 migration.

## What This Migration Ships

0.10.0 introduces the **Constitution split**: non-negotiable safety constraints
move out of the rulebase and into a separate, immutable file. Amendments to the
constitution require explicit human approval and **do not flow through the
rule-evolution workflow**.

The migration applies the following changes to a 0.9.0 generated repo:

- installs `.agent/constitution.md` (rendered from `core/constitution.template.md`)
  containing four sections - Discipline Gates, Forbidden Without Explicit
  Human Approval, Database & Migration Invariants, and Amendment;
- patches `.agent/rulebase.md` additively to insert a pointer blockquote
  immediately under the title. The patch is **idempotent** (`skip_if_contains`
  on `.agent/constitution.md`) and **preserves customization**: it does not
  remove or rewrite any existing rulebase content. Repos that copied policy
  text into the rulebase keep that text - the constitution file becomes the
  authoritative source going forward, but the inline copy is harmless;
- updates `.agent/workflows/rule-evolution-workflow.md` to add an `Out Of
  Scope` section that explicitly states the workflow does not edit
  `.agent/constitution.md`;
- ships the latest `scripts/lib/validate_agent_system.py` so generated
  validation enforces the constitution + rulebase pointer pair and the new
  token budget for `.agent/constitution.md` (100 lines);
- ships `scripts/lib/gate_modes.py`. The Stage 1 hardening work (post
  v0.9.0) made the validator depend on `gate_modes`, but the v0.9.0
  release predated that helper. Existing 0.9.0 repos do not have the
  helper on disk, so the 0.10.0 migration installs it alongside the new
  validator to keep the import resolvable;
- updates `.agent/manifest.json::canonical_files` to include
  `.agent/constitution.md` and bumps the manifest sync metadata to 0.10.0.

The migration **does not** install the optional `pre-tool-use-rulebase-guard.py`
hook. Hook templates remain off by default and can only be staged on a fresh
bootstrap or by manually copying the template from
`core/hooks/pre-tool-use-rulebase-guard.py.template`. Bootstrap never registers
hooks in harness settings.

## Conditional File Policy

The migration uses unconditional `safe_overwrite` entries for files that are
expected to exist in every 0.9.0 generated repo. Customized targets still
conflict by default. Review the conflict and pass `--accept-theirs <path>`
only when the 0.10.0 template version should replace the target copy.

The rulebase patch always targets `.agent/rulebase.md`. If the rulebase has
been customized so that the anchor `This file is the highest-priority
project-specific rule source for agents.` no longer matches exactly once,
the migration aborts with a clear conflict so the operator can decide where
to place the pointer.

## Verification

`tests/migrations/0.10.0/run.sh` builds a genuine 0.9.0 fixture from the
canonical 0.3.0 baseline (via multi-hop sync), applies 0.10.0, asserts the
constitution file, the rulebase pointer, the workflow Out-Of-Scope section,
the manifest version bump, the new `canonical_files` entry, generated
validator pass, and idempotent re-apply.
