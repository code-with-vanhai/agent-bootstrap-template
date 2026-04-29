# Spec: Data Surface section + `data-safety` skill (P1-3)

**Status:** Verified with evidence: agent-validate.sh @ 2026-04-29T09:02:14Z (exit=0)
**Date:** 2026-04-29
**Ref commit:** `083a310`
**Plan location note:** Stored under `docs/plans/bootstrap-090/p1-3-data-surface/` because this template repo dogfoods plans there. Generated target repos should use `.agent/runs/<date>-<slug>/`.
**Track:** 0.9.0 P1-3, after P0-1–P0-4, P1-1, P1-4 landed on `main`.

## Problem

The bootstrapped `.agent/` system has explicit governance for code, gates, secrets, and rules, but no first-class artifact for **data**. `core/project-profile.template.md` covers stack, repository map, public contracts, and dangerous operations, yet it never asks the operator to enumerate which paths read/write production data, which fields carry PII, which migrations are destructive, which exports leak data outside the trust boundary, or which logs must avoid customer-identifying values. Today an agent editing an ETL script, a migration, an export job, or an analytics emitter has no governance hook to consult before touching data — only the indirect `no-secret-leakage` skill, which is scoped to `.env`/credentials, not production data.

P1-3 closes this gap with two minimal, paired changes:

1. Add a `## Data Surface` section to `core/project-profile.template.md` so every bootstrapped repo records its data inventory, classification, and danger zones honestly (or marks each row `not configured` per existing convention).
2. Add a 9th optional native behavior skill, `data-safety`, that triggers on data-touching paths and enforces the discipline of consulting the `Data Surface` section before edits, with hard-gate text mirroring the existing `no-secret-leakage`/`scoped-implementation` shape.

Both changes are deliberately framed as additions, not redesigns: the manifest mechanism delivered in P0-1 was explicitly built to absorb skill #9 with a one-line manifest edit and no validator code change. P1-3 exercises that contract.

## Goals

- Insert a new `## Data Surface` section into `core/project-profile.template.md` between `## Public Contracts` and `## Dangerous Operations`. The section enumerates: PII columns/fields, customer-owned records, audit logs, analytics events, exports/integrations, and destructive operations specific to data. Every row uses the existing `{{...}}` placeholder convention; unknown placeholders render to the bootstrap-completion marker, so generated validation catches incomplete bootstrap work after `.agent/bootstrap-pending.md` is removed while raw placeholder scanning remains a secondary guard for unreplaced template tokens.
- Add `core/skills/data-safety/SKILL.md` modeled on `core/skills/no-secret-leakage/SKILL.md`: trigger-style `description: Use when …`, a hard-gate block, pre-action steps that re-read `.agent/project-profile.md` Data Surface plus `.agent/rulebase.md` and `.agent/ownership.md`, red flags, and a `## Canonical Sources` list referencing `.agent/project-profile.md`, `.agent/rulebase.md`, `.agent/ownership.md`.
- Add `data-safety` to `core/skills/manifest.json` (the canonical source of truth from P0-1). No validator code edit is required because `validate_skill_set`, `validate_skill_mapping`, and `validate_skill_count_docs` are all manifest-driven.
- Add a `data-safety` row to the `## Skill Mapping` table in `core/skills/README.md`.
- Update the README skill-count line from "Eight optional native behavior skills" to "Nine optional native behavior skills" and append `data-safety` to the inline list. The validator's `validate_skill_count_docs` enforces this drift automatically.
- Update prose enumerations that already list project-profile sections to include "data surface": `core/bootstrap-steps.md` step 3 and `scripts/bootstrap-request.sh` pending-checklist text. `core/instantiation-prompt.md` adds a one-line "Data surface" bullet alongside "Public surface" and "Dangerous operations".
- Preload `data-safety` on the implementer Claude subagent only, mirroring the precedent set by `no-secret-leakage`. Planner, reviewer, and gate-runner stay unchanged because they are not the primary data-write actors.
- Extend `validate_agent_system.py` with template-mode and generated-mode invariants that (a) `core/project-profile.template.md` (and rendered `.agent/project-profile.md`) contain a `## Data Surface` heading and (b) the implementer subagent (`.claude/agents/implementer.md`) lists `data-safety` in its `skills:` frontmatter when generated under `--harness claude --features full`.
- Update the regression fixture in `scripts/lib/test_validate_agent_system.py::test_template_stale_skill_count_doc_fails` from "Eight optional native behavior skills" → "Seven optional native behavior skills" replacement to "Nine optional native behavior skills" → "Seven optional native behavior skills" replacement so the docs-drift test continues to assert on the canonical phrase.

## Non-Goals

- No new gate mode, no new harness, no new manifest schema version. `core/skills/manifest.json` remains `schema_version: 1`; only the `skills` array gets one new entry.
- No new validator infrastructure for skills. The P0-1 manifest contract is the explicit reason this addition is one file plus one JSON line; if anything beyond that is required, the design is wrong.
- No automatic data classification or scanning. The `Data Surface` section is human-filled at bootstrap time, like every other section in `project-profile.template.md`.
- No mutation of the target repo's `.gitignore`, no log file, no telemetry. P1-3 stays in the static governance layer.
- No rewrite of `Dangerous Operations`. That section continues to enumerate destructive runbook commands; the new `Data Surface` section enumerates data assets and is consulted *before* invoking anything from `Dangerous Operations`.
- No change to `no-secret-leakage`. Secrets and production data are adjacent but distinct trust domains; collapsing them would weaken both skills' triggers.
- No new role or workflow file. `data-safety` is a behavior-shaping skill, not a process; if a Data Safety Review workflow becomes necessary it lives in P1-6+.
- No subagent-level enforcement. The implementer subagent gets `data-safety` in its `skills:` preload so Claude surfaces the skill at trigger time, but Codex/Cursor/Copilot harnesses pick up the skill via their normal native-skill discovery only when the harness supports it (existing P0-1 contract).

## Skill Definition (drafted)

```text
---
name: data-safety
description: Use when touching production data, PII, customer records, audit logs, analytics events, database migrations, ETL/ingestion code, exports, integrations, or any path that reads or writes user-owned or operator-owned data.
---

# Data Safety

Agents must not silently expose, modify, delete, or normalize data that belongs to users, customers, operators, or auditors.

## Hard Gate

```text
NO PRODUCTION DATA EXPOSURE, PII LEAKAGE, OR DESTRUCTIVE DATA OPERATIONS
WITHOUT EXPLICIT HUMAN APPROVAL
```

Before touching data-adjacent files or behavior:

1. Re-read `.agent/project-profile.md` (Data Surface section) and `.agent/rulebase.md`.
2. Confirm whether the touched path is listed under PII, audit, analytics, exports, or destructive operations; if it is not, stop and ask whether the inventory is incomplete before editing.
3. Do not invent fixtures with realistic-looking PII. Use clearly synthetic data and document the source.
4. For migrations and exports, state the rollback or revoke path in the run plan before editing.
5. Run the configured data/security gates or report `not configured` honestly.

## Red Flags

- "I'll just log the request body to debug this."
- "This script needs the real customer ids; tests can use prod for now."
- "I will drop this column; we can recreate it from backups."
- "The export is internal-only, so it doesn't need PII redaction."
- "The audit log is append-only, so this delete doesn't matter."

## Canonical Sources

- `.agent/project-profile.md` (Data Surface)
- `.agent/rulebase.md`
- `.agent/ownership.md`
```

## Project Profile section (drafted)

```text
## Data Surface

Record what data this repo touches so agents can recognize data-impacting changes before editing. Use `not configured` or `none` honestly; do not invent rows.

| Surface | Path or system | Classification | Notes |
|---|---|---|---|
| User-identifying fields | `{{PII_PATH_OR_NONE}}` | `{{PII_CLASSIFICATION_OR_NONE}}` | `{{PII_NOTES_OR_NONE}}` |
| Customer records | `{{CUSTOMER_RECORDS_PATH_OR_NONE}}` | `{{CUSTOMER_RECORDS_CLASSIFICATION_OR_NONE}}` | `{{CUSTOMER_RECORDS_NOTES_OR_NONE}}` |
| Audit / compliance logs | `{{AUDIT_LOG_PATH_OR_NONE}}` | `{{AUDIT_LOG_CLASSIFICATION_OR_NONE}}` | `{{AUDIT_LOG_NOTES_OR_NONE}}` |
| Analytics / telemetry events | `{{ANALYTICS_PATH_OR_NONE}}` | `{{ANALYTICS_CLASSIFICATION_OR_NONE}}` | `{{ANALYTICS_NOTES_OR_NONE}}` |
| Exports / external integrations | `{{EXPORT_PATH_OR_NONE}}` | `{{EXPORT_CLASSIFICATION_OR_NONE}}` | `{{EXPORT_NOTES_OR_NONE}}` |
| Destructive data operations | `{{DESTRUCTIVE_DATA_PATH_OR_NONE}}` | `{{DESTRUCTIVE_DATA_CLASSIFICATION_OR_NONE}}` | `{{DESTRUCTIVE_DATA_NOTES_OR_NONE}}` |

Data-touching changes must reference this table in the run plan and re-run the relevant gate or, if no gate exists, mark it `not configured` with the missing scanner named.
```

## Failure-mode Contract

- Adding skill #9 must not break repos that bootstrap without `--features full`. Skills are still emitted only when the harness supports native skill output; that decision is gated by `bootstrap-request.sh::copy_skills` and the existing `--features full` requirement, both unchanged in this plan.
- The `validate_skill_count_docs` invariant must continue to derive `expected_count` from `len(manifest.skills)`; we do not introduce a hard-coded `9`.
- Adding the implementer subagent skill preload must not regress generated-validator checks for `--harness claude --features full`. Test extends, does not replace, the existing assertion.
- The `## Data Surface` heading invariant in `validate_template`/`validate_generated` must use `contains(...)` against the literal heading; no regex with anchors that could break under user editing of the section body.
- The regression test fixture for stale skill count must be updated atomically with the README skill-count line; otherwise the unit-test suite fails the moment the README is fixed. Both edits land in the same commit.

## Validation Expectations

- `scripts/lib/validate_agent_system.py` template mode asserts:
  - `core/skills/manifest.json` parses, has 9 entries (set comparison, not literal `9`), and `data-safety` is in the set.
  - `core/skills/data-safety/SKILL.md` exists, has `name: data-safety`, has trigger-style description, has a `Canonical Sources` heading.
  - `core/project-profile.template.md` contains `## Data Surface`.
  - `README.md` skill-count line matches `len(manifest.skills) == 9`.
  - `core/skills/README.md` Skill Mapping table includes the `data-safety` row.
- `scripts/lib/validate_agent_system.py` generated mode asserts:
  - `.agent/project-profile.md` contains `## Data Surface` (rendered from the template).
  - When the manifest declares `claude-native-subagents`, `.claude/agents/implementer.md` `skills:` frontmatter line contains `data-safety` alongside the existing entries.
- `scripts/lib/test_validate_agent_system.py` adds:
  - `test_template_data_safety_skill_present_in_manifest_and_files` (positive).
  - `test_template_data_safety_missing_from_manifest_fails` (negative — remove from manifest, run validator, expect failure).
  - `test_template_project_profile_template_missing_data_surface_fails` (negative — strip section, expect failure).
  - `test_bootstrap_implementer_subagent_includes_data_safety_skill` (smoke — bootstrap claude/full, read implementer.md, assert frontmatter contains `data-safety`).
  - Updates `test_template_stale_skill_count_doc_fails` source string from `Eight` → `Nine`.
- `scripts/agent-validate.sh` passes against the source repo.
- `python3 -m unittest scripts.lib.test_validate_plan scripts.lib.test_gate_discovery scripts.lib.test_validate_agent_system scripts.lib.test_insert_gate_candidates scripts.lib.test_audit_log` passes (count rises by ~4 new tests).
- `scripts/agent-evals.sh --fast` passes (no new eval fixture introduced; this is a static governance change).
- Strict plan validation passes on this plan (`--force --strict docs/plans/bootstrap-090/p1-3-data-surface`).
