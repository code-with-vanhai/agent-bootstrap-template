# Plan: Three-tier thin adapter rules (P0-4)

**Status:** Verified with evidence: agent-validate.sh @ 2026-04-29T04:39:59Z (exit=0); `python3 -m unittest scripts.lib.test_validate_plan scripts.lib.test_gate_discovery scripts.lib.test_validate_agent_system` 87 pass; `bash scripts/agent-evals.sh --fast`; strict plan validation on this directory
**Date:** 2026-04-29
**Ref commit:** `2291636` (pre-implementation; `validate_agent_system` adapter loop evidence is `historical-code`)
**Plan location note:** Stored under `docs/plans/bootstrap-090/p0-4-three-tier-adapter-rules/` because this template repo dogfoods plans there; generated target repos should use `.agent/runs/<date>-<slug>/`.

## Goal

Add `## Always do`, `## Ask first`, `## Never do`, and `## Commands` to every thin adapter under `adapters/`, keep them as pointers to `.agent/`, and teach the structured validator to require those headings for present adapter files in generated repos and for all five source adapters in template mode.

## Run Artifact

`docs/plans/bootstrap-090/p0-4-three-tier-adapter-rules/{spec.md,plan.md}`

## Affected Areas

- `adapters/AGENTS.md`, `adapters/CLAUDE.md`, `adapters/GEMINI.md`, `adapters/cursor-agent-system.mdc`, `adapters/copilot-instructions.md` — add tier sections; preserve `.agent/` pointer and thin-file rule.
- `scripts/lib/validate_agent_system.py` — `validate_template`: assert five adapter sources exist and include tier headings plus `.agent/`. `validate_generated`: extend existing adapter loop to check tier headings when each path exists.
- `scripts/lib/test_validate_agent_system.py` — regression: strip a heading from a template copy and expect template validation to fail; optional positive check that generic bootstrap `AGENTS.md` contains all four headings.

## Owner

Implementer. Reviewer confirms heading strings are exact matches and generated-mode remains skip-based for absent adapters.

## Implementation Plan

1. Add module-level constants for the five template-relative adapter paths and the four exact heading lines.
2. Add `validate_thin_adapter_file(rel: str, *, require_exists: bool)` (or split template vs generated helpers) that: requires `.agent/` substring; requires each `## Always do`, `## Ask first`, `## Never do`, `## Commands`.
3. Call the template-side check from `validate_template()` after `validate_hook_templates()`, iterating `adapters/AGENTS.md` through `adapters/copilot-instructions.md`.
4. Extend the generated-mode `for adapter in (...)` loop to call tier-heading checks when `path.exists()` (after the `.agent/` check).
5. Rewrite each adapter markdown/mdc to include the four sections with concise bullets aligned to the existing canonical read list, `agent:<name>`, and `scripts/agent-eval.sh`. Keep frontmatter-only preamble unchanged for `cursor-agent-system.mdc`.
6. Add `test_template_adapter_missing_tier_heading_fails` using `make_template_copy`, delete one heading from `adapters/AGENTS.md`, run `--mode template --format json`, assert failure message mentions the heading.
7. Add `test_generated_agents_md_includes_adapter_tiers` (or fold into existing pass test) that bootstraps generic `standard`, reads `AGENTS.md`, asserts the four headings exist.
8. Run gated verification and update this plan’s status to `Verified` with evidence timestamps; convert any `current-code` blocks that drift after implementation to `historical-code`, keeping at least one `current-code` citation in `Existing Behaviors Preserved` that still matches the working tree (expected: `scripts/bootstrap-request.sh::copy_adapters`, unchanged by P0-4).

## Acceptance Criteria

| ID | Criterion | Verification Method | Gate |
|---|---|---|---|
| AC-1 | All five `adapters/*` files contain the four tier headings | `AUTOMATED-INTEGRATION` | `scripts/agent-validate.sh` (template mode) |
| AC-2 | Generated generic repo: `AGENTS.md` has four headings | `AUTOMATED-UNIT` | `python3 -m unittest scripts.lib.test_validate_agent_system` |
| AC-3 | Generated Claude repo: `AGENTS.md` and `CLAUDE.md` both have four headings | `AUTOMATED-UNIT` | same |
| AC-4 | Missing `## Always do` in template copy fails template validation | `AUTOMATED-UNIT` | same |
| AC-5 | Absent `CLAUDE.md` in generic bootstrap does not fail validation | `AUTOMATED-UNIT` | existing generic tests still pass |
| AC-6 | `scripts/agent-validate.sh`, unittests (plan + gate_discovery + validate_agent_system), `scripts/agent-evals.sh --fast`, strict plan validation | `AUTOMATED-INTEGRATION` | listed commands |

## Evidence

Pre-implementation grounding at `2291636`:

<!-- historical-code path=scripts/lib/validate_agent_system.py lines=571-579 ref=2291636 region_sha256=82127d6ebdfa6567a105dca4488fc34415712537cee2c3b288edb7b7ff43b838 -->
```python
        for adapter in ("AGENTS.md", "CLAUDE.md", "GEMINI.md", ".cursor/rules/agent-system.mdc", ".github/copilot-instructions.md"):
            path = self.root / adapter
            if path.exists():
                if ".agent/" in read_text(path):
                    self.pass_(f"{adapter} points to .agent/", adapter)
                else:
                    self.fail(f"{adapter} exists but does not point to .agent/", adapter)
            else:
                self.skip(f"{adapter} not generated", adapter)
```
<!-- /historical-code -->

<!-- current-code path=scripts/bootstrap-request.sh lines=430-449 ref=2291636 region_sha256=eab8c1bb4c5e8e036686c3c870f712aa83b51909a5578f37f35630cec848bd79 -->
```bash
copy_adapters() {
  copy_file "$TEMPLATE_ROOT/adapters/AGENTS.md" "$TARGET_ROOT/AGENTS.md"

  case "$harness" in
    claude)
      copy_file "$TEMPLATE_ROOT/adapters/CLAUDE.md" "$TARGET_ROOT/CLAUDE.md"
      ;;
    cursor)
      copy_file "$TEMPLATE_ROOT/adapters/cursor-agent-system.mdc" "$TARGET_ROOT/.cursor/rules/agent-system.mdc"
      ;;
    copilot)
      copy_file "$TEMPLATE_ROOT/adapters/copilot-instructions.md" "$TARGET_ROOT/.github/copilot-instructions.md"
      ;;
    gemini)
      copy_file "$TEMPLATE_ROOT/adapters/GEMINI.md" "$TARGET_ROOT/GEMINI.md"
      ;;
    codex|generic)
      ;;
  esac
}
```
<!-- /current-code -->

## Existing Behaviors Preserved

- `scripts/bootstrap-request.sh:430-449` — harness-specific adapter copy matrix is `PRESERVED`; P0-4 edits only `adapters/*` content, not bootstrap routing. Source:

<!-- current-code path=scripts/bootstrap-request.sh lines=430-449 ref=2291636 region_sha256=eab8c1bb4c5e8e036686c3c870f712aa83b51909a5578f37f35630cec848bd79 -->
```bash
copy_adapters() {
  copy_file "$TEMPLATE_ROOT/adapters/AGENTS.md" "$TARGET_ROOT/AGENTS.md"

  case "$harness" in
    claude)
      copy_file "$TEMPLATE_ROOT/adapters/CLAUDE.md" "$TARGET_ROOT/CLAUDE.md"
      ;;
    cursor)
      copy_file "$TEMPLATE_ROOT/adapters/cursor-agent-system.mdc" "$TARGET_ROOT/.cursor/rules/agent-system.mdc"
      ;;
    copilot)
      copy_file "$TEMPLATE_ROOT/adapters/copilot-instructions.md" "$TARGET_ROOT/.github/copilot-instructions.md"
      ;;
    gemini)
      copy_file "$TEMPLATE_ROOT/adapters/GEMINI.md" "$TARGET_ROOT/GEMINI.md"
      ;;
    codex|generic)
      ;;
  esac
}
```
<!-- /current-code -->

- `scripts/lib/validate_agent_system.py` — generated-mode adapter presence + `.agent/` pointer check is `EXTENDED` with tier-heading assertions inside the same branch where `path.exists()`; absent paths remain `SKIP` (see `historical-code` evidence block above for pre-P0-4 loop shape). Extension: `scripts/lib/validate_agent_system.py:607-617`.

## Verification

Pre-implementation:

```bash
scripts/agent-validate-plan.sh --force --strict docs/plans/bootstrap-090/p0-4-three-tier-adapter-rules
```

Post-implementation:

```bash
scripts/agent-validate.sh
python3 -m unittest scripts.lib.test_validate_plan scripts.lib.test_gate_discovery scripts.lib.test_validate_agent_system
bash scripts/agent-evals.sh --fast
scripts/agent-validate-plan.sh --force --strict docs/plans/bootstrap-090/p0-4-three-tier-adapter-rules
```

## Required Gates

- Strict plan validation before implementation starts.
- Template + generated validator gates and fast evals after implementation.

## Decision Ledger

| Decision | Chosen Behavior | Rationale | Alternatives Rejected | Caller/User Impact | Verification |
|---|---|---|---|---|---|
| Exact heading strings | Require `## Always do` etc. | Machine-checkable, matches user-facing spec | Free-form section titles; harder to validate | Consistent skim layout across harnesses | unittest + template validate |
| Generated scope | Tier headings only if adapter file exists | Avoids forcing Claude adapter on generic repos | Require all adapter files in every repo | Harness-minimal bootstrap stays valid | generic generated test |
| Template scope | All five `adapters/*` sources | Source of truth must be internally consistent | Validate only AGENTS.md | Copy drift across harnesses is caught early | agent-validate.sh template |

## Risks

- **Risk:** Heading typos break CI. **Mitigation:** constants + single helper; tests catch edits.
- **Risk:** Bullets grow and duplicate `.agent/rulebase.md`. **Mitigation:** keep bullets imperative and short; forbid pasting long rule text in adapters.
