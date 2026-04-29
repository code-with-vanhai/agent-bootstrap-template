# Plan: Data Surface section + `data-safety` skill (P1-3)

**Status:** Verified with evidence: agent-validate.sh @ 2026-04-29T09:02:14Z (exit=0)
**Date:** 2026-04-29
**Ref commit:** `083a310`
**Plan location note:** Stored under `docs/plans/bootstrap-090/p1-3-data-surface/`. Generated target repos should use `.agent/runs/<date>-<slug>/`.

## Goal

Add a 9th optional native behavior skill, `data-safety`, plus a paired `## Data Surface` section to `core/project-profile.template.md`. Both pieces are pure additions that exercise the manifest-driven skill mechanism delivered by P0-1: a single new entry in `core/skills/manifest.json` plus the new skill directory, with no validator code refactor, no manifest schema bump, and no harness/feature-flag changes. The new `Data Surface` section gives every bootstrapped repo a place to record PII paths, audit logs, analytics events, exports, and destructive data operations so the new skill has a concrete `.agent/`-side inventory to consult.

## Run Artifact

`docs/plans/bootstrap-090/p1-3-data-surface/{spec.md,plan.md}`

## Affected Areas

- `core/skills/manifest.json` (MODIFIED) — append `"data-safety"` to the `skills` array. Source of truth for `validate_skill_set`, `validate_skill_mapping`, `validate_skill_count_docs`.
- `core/skills/data-safety/SKILL.md` (NEW) — skill definition modeled on `core/skills/no-secret-leakage/SKILL.md`. Trigger-style description, hard-gate block, pre-action steps citing the new `Data Surface` section, red flags, `Canonical Sources` list pointing to `.agent/project-profile.md`, `.agent/rulebase.md`, `.agent/ownership.md`.
- `core/skills/README.md` (MODIFIED) — append a `data-safety` row to the `Skill Mapping` table. `parse_skill_mapping_names` already drives the validator's `validate_skill_mapping` from this table.
- `core/project-profile.template.md` (MODIFIED) — insert `## Data Surface` between `## Public Contracts` and `## Dangerous Operations`. Six placeholder rows covering PII fields, customer records, audit logs, analytics, exports, destructive data ops. Unknown placeholders render to the bootstrap-completion marker, so generated validation catches incomplete bootstrap work after `.agent/bootstrap-pending.md` is removed. Body text reminds the operator to use `not configured` honestly.
- `core/bootstrap-steps.md` (MODIFIED) — extend the step-3 enumeration to include "data surface" alongside "stack, runtime, public surface, dangerous operations, and repository map".
- `core/instantiation-prompt.md` (MODIFIED) — add a "Data surface" bullet alongside "Public surface" and "Dangerous operations".
- `scripts/bootstrap-request.sh` (MODIFIED) — pending-checklist text extension at line 792 to include "data surface"; implementer subagent `agent_skills` (line 563) extended with `data-safety`. No new feature flag, no copy-script change (`copy_skills` already globs `core/skills/*/SKILL.md`).
- `README.md` (MODIFIED) — line 44 word-form skill count "Eight" → "Nine" and inline list extended with `, and data-safety`.
- `scripts/lib/validate_agent_system.py` (MODIFIED) — template-mode `validate_template` adds two `contains` checks: `## Data Surface` heading in `core/project-profile.template.md` and the new `data-safety` skill name in `core/skills/manifest.json`. Generated-mode `validate_generated` adds the `## Data Surface` heading check against `.agent/project-profile.md` and (when `claude-native-subagents` is in `features_enabled`) a `data-safety` token check inside the `skills:` frontmatter line of `.claude/agents/implementer.md`. No edits to skill-count, skill-set, or skill-mapping logic — those already derive from manifest.
- `scripts/lib/test_validate_agent_system.py` (MODIFIED) — update the regression fixture in `test_template_stale_skill_count_doc_fails` from `"Eight optional native behavior skills"` to `"Nine optional native behavior skills"`. Add four positive/negative tests covering the new skill, the project-profile section, and the implementer subagent preload.
- `CHANGELOG.md` (MODIFIED) — entry under the unreleased 0.9.0 section noting the new `data-safety` skill and `Data Surface` section.

## Owner

Implementer. Reviewer must verify (1) the manifest mechanism delivered in P0-1 absorbs skill #9 with no validator-internal changes beyond the two new `contains` checks, (2) the `## Data Surface` heading is placed between `## Public Contracts` and `## Dangerous Operations` so existing references in `core/bootstrap-steps.md`/`core/instantiation-prompt.md` stay coherent, and (3) the regression fixture in `test_template_stale_skill_count_doc_fails` is updated atomically with the README skill-count line.

## Implementation Plan

1. Add `core/skills/data-safety/SKILL.md` modeled on `core/skills/no-secret-leakage/SKILL.md`. Frontmatter `name: data-safety`, `description: Use when ...`. Body sections: `# Data Safety`, `## Hard Gate` with the verbatim text `NO PRODUCTION DATA EXPOSURE, PII LEAKAGE, OR DESTRUCTIVE DATA OPERATIONS\nWITHOUT EXPLICIT HUMAN APPROVAL`, numbered pre-action steps that re-read `.agent/project-profile.md` (Data Surface) and `.agent/rulebase.md`, `## Red Flags`, `## Canonical Sources` listing `.agent/project-profile.md` (Data Surface), `.agent/rulebase.md`, `.agent/ownership.md`. Description text wording is finalized in `Spec § Skill Definition`.
2. Append `"data-safety"` to the `skills` array in `core/skills/manifest.json`. Keep declaration order matching the existing Skill Mapping table convention; new entry appears last so reviewers see the addition without churn on existing rows.
3. Append a row to the `Skill Mapping` table in `core/skills/README.md`:
   ```text
   | `data-safety` | `.agents/skills/agent-bootstrap/data-safety/SKILL.md` or `.claude/skills/agent-bootstrap/data-safety/SKILL.md` | `.agent/project-profile.md`, `.agent/rulebase.md`, `.agent/ownership.md` |
   ```
4. Insert the `## Data Surface` section in `core/project-profile.template.md` immediately before the existing `## Dangerous Operations` heading (i.e., after the closing line of `## Public Contracts`). Section body uses the table shape drafted in `Spec § Project Profile section`. Use the existing `{{...}}` placeholder convention; unknown placeholders render to the bootstrap-completion marker, and `validate_generated` catches remaining bootstrap-completion markers after `.agent/bootstrap-pending.md` is removed while raw placeholder scanning remains a secondary guard for unreplaced template tokens.
5. Update README skill-count line: `core/skills/manifest.json` shows the canonical 9-entry list; `README.md` line 44 word form goes from `Eight` to `Nine` and the inline enumeration appends `, and data-safety`. The validator's `validate_skill_count_docs` enforces `len(manifest.skills) == 9` automatically through `skill_count_mentions`.
6. Update prose enumerations:
   - `core/bootstrap-steps.md` step 3: "stack, runtime, public surface, **data surface**, dangerous operations, and repository map".
   - `core/instantiation-prompt.md`: add a one-line bullet `Data surface: PII fields, customer records, audit logs, analytics events, exports, destructive data operations.` between the existing `Public surface` and `Dangerous operations` bullets.
   - `scripts/bootstrap-request.sh:792`: pending-checklist text now reads "stack, framework, runtime, public surface, **data surface**, dangerous operations, and repository map".
7. Extend the implementer Claude subagent preload in `scripts/bootstrap-request.sh:557-564`. Change `agent_skills="scoped-implementation, no-invented-artifacts, no-secret-leakage"` to `agent_skills="scoped-implementation, no-invented-artifacts, no-secret-leakage, data-safety"`. Planner, reviewer, gate-runner remain unchanged because they are not the data-write actors.
8. Extend `scripts/lib/validate_agent_system.py`:
   - In `validate_template`, add two `self.contains(...)` calls:
     - `core/project-profile.template.md` contains `"## Data Surface"`.
     - `core/skills/manifest.json` contains `"data-safety"` (defensive double-check; the manifest-derived skill set check would also fail without the entry, but the literal `contains` check yields a clearer failure message).
   - In `validate_generated`, when `.agent/project-profile.md` is present, assert it contains `"## Data Surface"`. When the manifest declares `claude-native-subagents`, additionally assert `.claude/agents/implementer.md` contains `"data-safety"` on its `skills:` frontmatter line (regex anchored to `^skills:`).
9. Update `scripts/lib/test_validate_agent_system.py`:
   - Patch `test_template_stale_skill_count_doc_fails` source string from `"Eight optional native behavior skills"` to `"Nine optional native behavior skills"`. The replacement target stays `"Seven optional native behavior skills"` so the negative path still asserts on a count mismatch.
   - Add `test_template_data_safety_skill_present_in_manifest_and_files`: positive smoke that the manifest, the SKILL.md, and the Skill Mapping row all reference `data-safety`.
   - Add `test_template_data_safety_missing_from_manifest_fails`: rewrite manifest dropping `data-safety`, run validator with `--mode template`, assert non-zero exit and the message names the skill directory.
   - Add `test_template_project_profile_template_missing_data_surface_fails`: strip the `## Data Surface` line and assert the validator fails with a clear path.
   - Add `test_bootstrap_implementer_subagent_includes_data_safety_skill`: bootstrap claude/full into a temp target, read `.claude/agents/implementer.md`, assert the `skills:` line contains `data-safety`.
10. Update `CHANGELOG.md` under the unreleased 0.9.0 section: "Add `data-safety` optional behavior skill and `## Data Surface` section to `core/project-profile.template.md`. Skill #9 is added through the manifest mechanism introduced in P0-1; no validator refactor required."
11. Run gates listed in `Verification` and convert `current-code` evidence blocks below to `historical-code` for any region that the implementation changes (manifest, README line 44, bootstrap-request.sh implementer block, test fixture). At least one `current-code` block must remain in `Existing Behaviors Preserved` to satisfy `BEH-001`; `validate_skill_count_docs` and the `Public Contracts` template section are stable and stay `current-code`.
12. Update spec/plan status to `Verified with evidence: …` once gates are green.

## Existing Behaviors Preserved

- `scripts/lib/validate_agent_system.py::validate_skill_count_docs` continues to derive `expected_count = len(manifest.skills)` from `core/skills/manifest.json`; no hard-coded `9`. Citation: `current-code path=scripts/lib/validate_agent_system.py lines=297-316`. This is the load-bearing reason P1-3 is purely additive.

<!-- current-code path=scripts/lib/validate_agent_system.py lines=297-316 ref=083a310 region_sha256=11913816c28382d1af502574ca1acfafca1c98e075a6c40eeb920e27783919c6 -->
```python
    def validate_skill_count_docs(self, skills: list[str]) -> None:
        expected_count = len(skills)
        for rel in ("README.md", "USAGE.md", "core/skills/README.md"):
            path = self.root / rel
            if not path.is_file():
                self.skip(f"{rel} not present for skill count drift check", rel)
                continue
            mismatches = [
                phrase
                for phrase, count in skill_count_mentions(read_text(path))
                if count != expected_count
            ]
            if mismatches:
                self.fail(
                    f"{rel} has stale skill count mention(s): {', '.join(mismatches)}; "
                    f"expected {expected_count} skills from core/skills/manifest.json",
                    rel,
                )
            else:
                self.pass_(f"{rel} skill count mentions match manifest", rel)
```
<!-- /current-code -->

- `core/project-profile.template.md::Public Contracts` table is `PRESERVED`. The new `## Data Surface` heading inserts immediately after this section's closing blank line; no existing row, header, or path is renamed. Citation: `current-code path=core/project-profile.template.md lines=35-43`.

<!-- current-code path=core/project-profile.template.md lines=35-43 ref=083a310 region_sha256=6b5da9ed76c32238ece529d5c6f8d408dba3b816b27c7bbf99d92f9fb19e8a6d -->
```markdown
## Public Contracts

List contracts that must not change casually:

- API response/request shapes: `{{API_CONTRACT_PATH_OR_NOT_FOUND}}`
- Database schema and migrations: `{{SCHEMA_PATH_OR_NOT_FOUND}}`
- CLI commands: `{{CLI_DOC_PATH_OR_NOT_APPLICABLE}}`
- Package exports: `{{EXPORTS_PATH_OR_NOT_APPLICABLE}}`
- UI routes or deep links: `{{ROUTES_DOC_OR_NOT_APPLICABLE}}`
```
<!-- /current-code -->

- `core/skills/no-secret-leakage/SKILL.md` is the structural template for the new skill and is `PRESERVED VERBATIM`. The new `data-safety` skill mirrors its frontmatter shape, hard-gate block, pre-action numbered list, red flags list, and `## Canonical Sources` heading. Citation: `current-code path=core/skills/no-secret-leakage/SKILL.md lines=1-36`.

<!-- current-code path=core/skills/no-secret-leakage/SKILL.md lines=1-36 ref=083a310 region_sha256=27c44647891de47509da5e3a2ef7ce1af645663f5f87f45ab5609fea084b8eed -->
```markdown
---
name: no-secret-leakage
description: Use when touching .env files, credentials, tokens, private keys, auth config, logging, CI secrets, or any code path that may expose secrets.
---

# No Secret Leakage

Agents must not expose, edit, invent, or normalize secrets.

## Hard Gate

```text
NO SECRET, TOKEN, CREDENTIAL, PRIVATE KEY, OR .ENV VALUE LEAKAGE
```

Before touching secret-adjacent files or behavior:

1. Re-read `.agent/rulebase.md` and `.agent/gates.md`.
2. Do not edit secret values or `.env` values without explicit human approval.
3. Prefer placeholders or documented secret names over real values.
4. Run the configured security gate or report that secret scanning is `not configured`.
5. Report any skipped scanner and residual risk.

## Red Flags

- "I will paste the token temporarily."
- "The .env value looks harmless."
- "The scanner is missing, so this is safe."
- "I can add the real key and the user can rotate it later."
- Logging request headers, authorization values, cookies, private keys, or session tokens.

## Canonical Sources

- `.agent/rulebase.md`
- `.agent/gates.md`
- `scripts/agent-eval.sh security`
```
<!-- /current-code -->

- `scripts/bootstrap-request.sh::copy_skills` continues to glob `core/skills/*/SKILL.md` so the new `data-safety` directory flows into the target without a script edit. Citation: `path:line` reference at `scripts/bootstrap-request.sh:492-495`.
- `core/manifest.template.json` shape is `PRESERVED`; no new feature flag, no new field. Adding skill #9 does not require a manifest schema bump.
- `bin/agent-bootstrap` defaults stay unchanged. `data-safety` is automatically generated under `--features full --harness {claude,codex}`; non-skill harnesses skip skill output entirely (existing P0-1 contract).

## Existing Behaviors Changed

- `core/skills/manifest.json` array length grows from 8 to 9. Pre-change content is `historical-code` evidence below; the post-change file appends `"data-safety"` as the final entry.

<!-- historical-code path=core/skills/manifest.json lines=1-14 ref=083a310 region_sha256=e30825145dbf86694e35b7f4963a60ee33ccfdcaeb12481596b99fba5d54730d -->
```json
{
  "schema_version": 1,
  "skills": [
    "verify-before-completion",
    "root-cause-debugging",
    "scoped-implementation",
    "plan-before-code",
    "worktree-isolation",
    "no-invented-artifacts",
    "bootstrap-agent-system",
    "no-secret-leakage"
  ]
}
```

- `README.md` line 44 word-form skill count `BUG FIX`: `Eight` → `Nine` and inline list extended with `, and data-safety`. Validator `validate_skill_count_docs` enforces this drift automatically once the manifest grows.

<!-- historical-code path=README.md lines=44-44 ref=083a310 region_sha256=9e7443de362c04de21773f4de3e80561fda9538289c9484c07e48babc5e3731a -->
```markdown
- Eight optional native behavior skills: verify-before-completion, root-cause-debugging, scoped-implementation, plan-before-code, worktree-isolation, no-invented-artifacts, bootstrap-agent-system, and no-secret-leakage.
```

- `core/skills/README.md::Skill Mapping` table extends with the new `data-safety` row. Existing rows stay byte-for-byte unchanged.

<!-- historical-code path=core/skills/README.md lines=9-21 ref=083a310 region_sha256=8c575011d7ed1c297deadcfc1735fd82de9f877e17d14a8a6f4a1fff3275d8e5 -->
```markdown
## Skill Mapping

| Skill | Generated path | Canonical source to keep aligned |
|---|---|---|
| `verify-before-completion` | `.agents/skills/agent-bootstrap/verify-before-completion/SKILL.md` or `.claude/skills/agent-bootstrap/verify-before-completion/SKILL.md` | `.agent/gates.md`, `.agent/roles/gate-runner.md` |
| `root-cause-debugging` | `.agents/skills/agent-bootstrap/root-cause-debugging/SKILL.md` or `.claude/skills/agent-bootstrap/root-cause-debugging/SKILL.md` | `.agent/workflows/bugfix-workflow.md`, `.agent/rulebase.md` |
| `scoped-implementation` | `.agents/skills/agent-bootstrap/scoped-implementation/SKILL.md` or `.claude/skills/agent-bootstrap/scoped-implementation/SKILL.md` | `.agent/ownership.md`, `.agent/roles/implementer.md`, `.agent/rulebase.md` |
| `plan-before-code` | `.agents/skills/agent-bootstrap/plan-before-code/SKILL.md` or `.claude/skills/agent-bootstrap/plan-before-code/SKILL.md` | `.agent/roles/planner.md`, `.agent/runs/` convention |
| `worktree-isolation` | `.agents/skills/agent-bootstrap/worktree-isolation/SKILL.md` or `.claude/skills/agent-bootstrap/worktree-isolation/SKILL.md` | `.agent/workflows/worktree-workflow.md` when enabled |
| `no-invented-artifacts` | `.agents/skills/agent-bootstrap/no-invented-artifacts/SKILL.md` or `.claude/skills/agent-bootstrap/no-invented-artifacts/SKILL.md` | `.agent/rulebase.md`, `.agent/gates.md`, `.agent/project-profile.md` |
| `bootstrap-agent-system` | `.agents/skills/agent-bootstrap/bootstrap-agent-system/SKILL.md` or `.claude/skills/agent-bootstrap/bootstrap-agent-system/SKILL.md` | `.agent/bootstrap-pending.md`, `scripts/bootstrap-request.sh`, `core/bootstrap-steps.md` |
| `no-secret-leakage` | `.agents/skills/agent-bootstrap/no-secret-leakage/SKILL.md` or `.claude/skills/agent-bootstrap/no-secret-leakage/SKILL.md` | `.agent/rulebase.md`, `.agent/gates.md`, `scripts/agent-eval.sh security` |
```

- `scripts/bootstrap-request.sh::copy_claude_subagents` implementer branch extends the `agent_skills` line with `, data-safety`. Other roles unchanged.

<!-- historical-code path=scripts/bootstrap-request.sh lines=557-564 ref=083a310 region_sha256=d21c5a41426e167dae89a371c5d81ab8174872c15a7716d3bfbf1f243afe6e1e -->
```bash
      implementer)
        agent_description="Implement scoped changes for the current run spec. Read .agent/roles/implementer.md, the run plan, and .agent/rulebase.md before editing. Stay within the assigned ownership boundary, run scripts/agent-eval.sh, and stop on uncertainty."
        agent_tools="Read, Edit, Write, MultiEdit, Grep, Glob, Bash"
        agent_disallowed=""
        agent_permission_mode="default"
        agent_max_turns="60"
        agent_skills="scoped-implementation, no-invented-artifacts, no-secret-leakage"
        ;;
```

- `core/bootstrap-steps.md` step 3 enumeration extends to include `data surface`.

<!-- historical-code path=core/bootstrap-steps.md lines=37-37 ref=083a310 region_sha256=14157b5fafaa2d1467315731d223cc3d9361417b96cf703bc9aef4e5e11b71b9 -->
```markdown
3. Fill `.agent/project-profile.md` with observed stack, runtime, public surface, dangerous operations, and repository map.
```

- `core/instantiation-prompt.md` adds a `Data surface:` bullet between the existing `Public surface:` and `Dangerous operations:` bullets.

<!-- historical-code path=core/instantiation-prompt.md lines=41-43 ref=083a310 region_sha256=41885df12215c0c3e0f2a6af5335ab2dc0d1b0fa26543e25e86e5de4a52291d1 -->
```markdown
- Public surface: APIs, CLI, package exports, routes, schemas, config formats, docs usage.
- Dangerous operations: deploy, remote migration, data deletion, secret/key handling, production scripts.
- Ownership boundaries: at least root-level paths, and per-package boundaries for monorepos when obvious.
```

- `scripts/bootstrap-request.sh:792` pending-checklist text extends to mention `data surface`.

<!-- historical-code path=scripts/bootstrap-request.sh lines=792-792 ref=083a310 region_sha256=88fc6adfb1e0b8da474605105be7e88ae11a23272a6ec0a52f52cabb6ca0d944 -->
```bash
- [ ] Fill `.agent/project-profile.md` with the real stack, framework, runtime, public surface, dangerous operations, and repository map.
```

- `scripts/lib/test_validate_agent_system.py::test_template_stale_skill_count_doc_fails` swaps `"Eight"` for `"Nine"` in the source replacement so the regression continues to fire on a count mismatch.

<!-- historical-code path=scripts/lib/test_validate_agent_system.py lines=145-162 ref=083a310 region_sha256=ec6658845c8a9ff09296c3291b7c6e437e9d1d87b745475b4ea6110c2d50742f -->
```python
    def test_template_stale_skill_count_doc_fails(self):
        target = self.make_template_copy()
        readme = target / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8").replace(
                "Eight optional native behavior skills",
                "Seven optional native behavior skills",
            ),
            encoding="utf-8",
        )

        result = self.run_validator("--mode", "template", "--format", "json", cwd=target)

        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        messages = "\n".join(item["message"] for item in payload["results"])
        self.assertIn("README.md has stale skill count mention(s): Seven optional native behavior skills", messages)
```

## Acceptance Criteria

| ID | Criterion | Verification Method | Gate |
|---|---|---|---|
| AC-1 | `core/skills/manifest.json` parses as JSON, has `schema_version: 1`, has `skills` length 9, and the literal `data-safety` is in the array | `AUTOMATED-UNIT` | `python3 -m unittest scripts.lib.test_validate_agent_system` |
| AC-2 | `core/skills/data-safety/SKILL.md` exists, has frontmatter `name: data-safety`, has trigger-style description starting with `Use when`, and contains a `## Canonical Sources` heading | `AUTOMATED-UNIT` | same |
| AC-3 | `core/skills/README.md` Skill Mapping table parses to a 9-element set containing `data-safety` | `AUTOMATED-UNIT` | same |
| AC-4 | `core/project-profile.template.md` contains the literal heading `## Data Surface` between `## Public Contracts` and `## Dangerous Operations` | `AUTOMATED-UNIT` | same |
| AC-5 | After running `bash bin/agent-bootstrap` against a fresh target with `--harness claude --features full`, `.agent/project-profile.md` contains `## Data Surface` | `AUTOMATED-INTEGRATION` | `python3 -m unittest scripts.lib.test_validate_agent_system` (existing bootstrap test fixture) |
| AC-6 | After bootstrap with `--harness claude --features full`, `.claude/agents/implementer.md` `skills:` frontmatter line contains the literal token `data-safety` | `AUTOMATED-INTEGRATION` | same |
| AC-7 | `validate_skill_count_docs` against the source repo passes; `README.md` line 44 reads `Nine` and lists `data-safety`; replacing it with `Seven optional native behavior skills` causes the validator to fail | `AUTOMATED-UNIT` | `python3 -m unittest scripts.lib.test_validate_agent_system` |
| AC-8 | `bash scripts/agent-validate.sh` (template mode against this repo) passes after the change | `AUTOMATED-INTEGRATION` | `scripts/agent-validate.sh` |
| AC-9 | `bash scripts/agent-evals.sh --fast` passes | `AUTOMATED-INTEGRATION` | `scripts/agent-evals.sh --fast` |
| AC-10 | Strict plan validation passes pre-implementation | `AUTOMATED-INTEGRATION` | `scripts/agent-validate-plan.sh --force --strict docs/plans/bootstrap-090/p1-3-data-surface` |

## Decision Ledger

| Decision | Chosen Behavior | Rationale | Alternatives Rejected | Caller/User Impact | Verification |
|---|---|---|---|---|---|
| Skill #9 placement strategy | Add `data-safety` to `core/skills/manifest.json` only; rely on the P0-1 manifest-driven validator path | The whole point of P0-1 was to absorb skill #N+1 with a single JSON edit and zero validator-internal change. Doing anything else here would invalidate that contract. | (a) Hard-coded skill list in validator (rejected — P0-1 explicitly removed this); (b) New manifest field `data_skills: [...]` (rejected — duplicates the schema for no semantic gain). | Bootstrap consumers automatically get the new skill once they sync to 0.9.0. No new flag to remember. | `test_template_data_safety_skill_present_in_manifest_and_files`, `validate_skill_set`, `validate_skill_mapping` |
| Skill count delta size (8 → 9) | Manifest is the single source of truth; the README skill-count line and the regression-test fixture (`test_template_stale_skill_count_doc_fails`) are updated in the same commit so docs-drift never opens; validator derives `expected_count = len(manifest.skills)` so no hard-coded 9 appears anywhere except the README word form | The 0.7→0.8 and 0.8→0.9 history shows that hard-coded counts are a docs-drift risk; manifest + drift checker is the contract. The size budget here is a per-skill addition; total stays well under any reviewer-comprehension limit (current count 9 is still a list a human can read in one breath). | Hard-coded `9` in validator (rejected — recreates the brittleness P0-1 just removed); skip README count update and rely only on manifest (rejected — README is user-facing and must match). | A README reader sees the correct skill count; an agent reading `core/skills/manifest.json` sees nine entries; no consumer sees a mismatch. | `test_template_stale_skill_count_doc_fails` (fixture updated to use `Nine`), `validate_skill_count_docs` re-runs over README/USAGE/skills-README |
| `## Data Surface` placement in `project-profile.template.md` | Insert between `## Public Contracts` and `## Dangerous Operations` | The natural reading order is: what code surface is public → what data surface is touched → what destructive operations exist. Putting Data Surface before Dangerous Operations means the agent inventories data assets before it considers destructive runbook commands. | (a) End of file (rejected — agents skim top-down; section visibility matters); (b) Inside `Public Contracts` as a sub-bullet (rejected — data-vs-API contracts have different consumers and different gates). | An operator filling the template sees a data inventory prompt at the natural moment. An agent reading the rendered profile finds Data Surface adjacent to Dangerous Operations, where it is most useful. | `test_template_project_profile_template_missing_data_surface_fails`, `validate_template`/`validate_generated` `contains` checks |
| Subagent preload scope for `data-safety` | Preload only on the implementer Claude subagent; planner/reviewer/gate-runner stay unchanged | The implementer is the only role that writes to data-touching files. Planner produces specs (no edits), reviewer reads diffs (no edits), gate-runner executes verification scripts (no edits). Mirrors the existing precedent for `no-secret-leakage`, which is also implementer-only. | (a) Preload on planner too (rejected — adds context length without write-path coverage); (b) Preload on all four (rejected — context-budget cost without trigger benefit). | Claude implementer surfaces the skill at trigger time without inflating planner/reviewer prompts. Codex/Cursor harnesses still discover the skill via their normal native-skill mechanism when supported. | `test_bootstrap_implementer_subagent_includes_data_safety_skill`; bootstrap smoke + `.claude/agents/implementer.md` content check |
| Skill canonical-sources scope | `data-safety` Canonical Sources lists `.agent/project-profile.md` (Data Surface), `.agent/rulebase.md`, `.agent/ownership.md` | Project profile carries the inventory, rulebase carries the discipline gates, ownership carries the approval boundary. Excluding `.agent/gates.md` is intentional — there is no canonical "data" gate in the template; if a repo configures one, the operator updates the skill via the existing drift rule in `core/skills/README.md`. | Including `.agent/gates.md` (rejected — would imply a data gate that the template does not ship). | An agent following the skill knows exactly which three governance files to consult before editing. | Manual review against `core/skills/README.md::Drift Rule`; AC-2 ensures the heading exists |
| Project-profile template invariant check | New template/generated `contains("## Data Surface", ...)` checks anchor on the literal heading | Section bodies are operator-edited; only the heading is stable. Anchoring on the heading lets operators rewrite rows without breaking validation, while still catching accidental section deletion. | Anchoring on the table header row (rejected — too brittle, operators rename columns); anchoring on a `<!-- AGENT-DATA-SURFACE -->` HTML comment (rejected — adds boilerplate to a human-edited file). | Validators still catch the regression where someone deletes the section; operators can edit section content freely. | AC-4 (template), AC-5 (generated), validator `contains` calls |

## Contract Value Table

The new `data-safety` skill name and the `## Data Surface` heading become contract literals consumed by the validator and by every harness that reads `core/skills/manifest.json`.

| Literal | Producer | Consumer | User-facing behavior | Test |
|---|---|---|---|---|
| `data-safety` (skills array entry) | `core/skills/manifest.json` | `validate_skill_set`, `validate_skill_mapping`, `validate_skill_count_docs`, harness skill discovery | Operators see a 9th skill in `Skill Mapping`; harnesses load the SKILL.md when triggers match | `test_template_data_safety_skill_present_in_manifest_and_files`, `test_template_data_safety_missing_from_manifest_fails` |
| `name: data-safety` (frontmatter line) | `core/skills/data-safety/SKILL.md` | `validate_skill_set` (regex check on `^name: data-safety$`) | Harness loads the skill by name; mismatch hides the skill silently | `test_template_data_safety_skill_present_in_manifest_and_files` |
| `## Data Surface` (heading) | `core/project-profile.template.md`; rendered into `.agent/project-profile.md` | `validate_template`, `validate_generated`, the new `data-safety` skill's pre-action step #1 | Operators get a fixed inventory prompt; agents get a stable section to cite | `test_template_project_profile_template_missing_data_surface_fails`, AC-4, AC-5 |
| `Nine` (README skill-count word form) | `README.md` line 44 | `validate_skill_count_docs::skill_count_mentions::WORD_SKILL_COUNT_RE` | Reader sees the correct count | `test_template_stale_skill_count_doc_fails` (fixture updated) |

## Test Delta

| Test | Action | Why |
|---|---|---|
| `test_template_stale_skill_count_doc_fails` | UPDATE | Source string for the find-replace must move from `Eight` to `Nine` because the README will say `Nine` post-implementation; the test asserts the validator catches a stale-`Seven` regression |
| `test_template_data_safety_skill_present_in_manifest_and_files` | ADD | New positive smoke that manifest, SKILL.md, and Skill Mapping all reference `data-safety`; without it AC-1/AC-2/AC-3 have no automated coverage |
| `test_template_data_safety_missing_from_manifest_fails` | ADD | New negative test that the validator fails clearly if a future regression drops `data-safety` from the manifest while the directory still exists |
| `test_template_project_profile_template_missing_data_surface_fails` | ADD | New negative test that `validate_template` fails if `## Data Surface` is removed from `core/project-profile.template.md` |
| `test_bootstrap_implementer_subagent_includes_data_safety_skill` | ADD | New integration smoke that `--harness claude --features full` propagates the skill preload into `.claude/agents/implementer.md` |
| Existing `test_template_*` tests for skills, mapping, and count docs | KEEP | Manifest-driven validator path is preserved; their assertions automatically extend to the 9-entry case |

## Risks

- Risk: A user rebases this branch onto a future commit that already moves `core/project-profile.template.md` line numbers, invalidating evidence-block hashes for `current-code` blocks. Mitigation: at implementation time, run `scripts/agent-validate-plan.sh --force --strict` and refresh `region_sha256` for any block flagged stale; convert stale `current-code` to `historical-code` only when the post-impl region truly drifts.
- Risk: The new `## Data Surface` heading collides with an existing user-edited project profile that already added a custom section of the same name. Mitigation: bootstrap only writes `.agent/project-profile.md` once (sync logic refuses to overwrite); existing profiles are surfaced as a `SKIP` by `bootstrap-request.sh::copy_file`. Document the recommended manual merge path in the bootstrap pending checklist.
- Risk: The `data-safety` skill description triggers too aggressively (e.g., on every test fixture file). Mitigation: description is scoped to "production data, PII, customer records, audit logs, analytics events, database migrations, ETL/ingestion code, exports, integrations". Tests and synthetic fixtures fall outside that scope; if false-positive triggering becomes an issue, edit the description in a follow-up rather than diluting the hard gate.
- Risk: Validator `contains("## Data Surface", ...)` fires false-negative when the operator renames the heading (e.g., to `## Data Inventory`). Mitigation: this is the desired behavior — the section is a contract; renaming requires updating the skill's pre-action step #1 in the same change. The contract is documented in `core/skills/README.md::Drift Rule`.
- Risk: Implementer subagent prompt length grows by ~12 characters when `data-safety` is added. Mitigation: skills lists are CSV strings; this is well within Claude's frontmatter limits and matches the precedent for adding `no-secret-leakage` in P0-2/P0-3.
- Risk: The regression test fixture `test_template_stale_skill_count_doc_fails` could go stale if a future skill is added without updating its source string. Mitigation: the new tests `test_template_data_safety_*` plus `validate_skill_count_docs` enforce this drift on every PR; the next skill addition (P2.x) will surface the same fixture-update step in its plan.

## Rollback

- Revert the implementation commit (single commit recommended, mirroring P0-1/P0-2/P0-4/P1-1/P1-4 cadence). The manifest, the new SKILL.md, the Skill Mapping row, the project-profile section, the README count update, the implementer subagent skill list, the validator `contains` checks, and the test deltas are all in one commit.
- After revert, run `bash scripts/agent-validate.sh` and `python3 -m unittest scripts.lib.test_validate_agent_system` to confirm the tree is back to the pre-P1-3 invariants.
- Existing repos that have already synced past 0.9.0 will keep the skill until they sync forward to a version that drops it. There is no migration removal because skill files are additive and `agent-sync.py` does not auto-delete generated skill directories.

## Verification

- `bash scripts/agent-validate.sh` (template mode against this repo) passes.
- `python3 -m unittest scripts.lib.test_validate_plan scripts.lib.test_gate_discovery scripts.lib.test_validate_agent_system scripts.lib.test_insert_gate_candidates scripts.lib.test_audit_log` passes (count rises by ~4 new tests).
- `bash scripts/agent-evals.sh --fast` passes (no new fixture; this is a static governance change).
- `scripts/agent-validate-plan.sh --force --strict docs/plans/bootstrap-090/p1-3-data-surface` returns `0 High, 0 Medium`.
- Smoke bootstrap: `bash bin/agent-bootstrap --harness claude --features full --target /tmp/p13-smoke` produces `.agent/project-profile.md` with `## Data Surface`, `.claude/agents/implementer.md` with `data-safety` in `skills:`, and the generated validator returns `failure_count: 0`.
