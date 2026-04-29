# Spec: Three-tier thin adapter rules (P0-4)

**Status:** Verified with evidence: agent-validate.sh @ 2026-04-29T04:39:59Z (exit=0); unittests 87 pass (incl. validate_agent_system); agent-evals `--fast`; strict plan re-validation
**Date:** 2026-04-29
**Ref commit:** `2291636` (pre-implementation anchor; P0-4 impl in working tree)
**Plan location note:** Stored under `docs/plans/bootstrap-090/p0-4-three-tier-adapter-rules/` because this template repo dogfoods plans under `docs/plans/`. Generated target repos should use `.agent/runs/<date>-<slug>/`.
**Track:** 0.9.0 P0-4, batch with P0-1–P0-3 landed on `main`.

## Problem

Repository-local adapters (`AGENTS.md`, `CLAUDE.md`, harness-specific pointers) already tell agents to use `.agent/` as canonical instructions, but they do not structure **priorities** into a compact tier list that tools and humans can skim before delegating. A three-tier pattern (`Always do`, `Ask first`, `Never do`) plus explicit `Commands` reduces ambiguity when the adapter is the only surface a harness loads.

Without validator coverage, adapters can drift from each other or lose required section headings after edits.

## Goals

- Add four markdown sections to each thin adapter under `adapters/`: `## Always do`, `## Ask first`, `## Never do`, `## Commands`.
- Keep adapters thin: long-lived rules stay in `.agent/`; adapters only prioritize and point back.
- Extend `scripts/lib/validate_agent_system.py` **template** mode to require the four headings on all five source adapter files.
- Extend **generated** mode to require the four headings only on adapter files that **exist** in the target repo (same paths as today: `AGENTS.md`, optional harness-specific files). Do not require `CLAUDE.md` for generic-only bootstrap.
- Add regression tests: happy path for generic and harness-specific bootstrap; failure when a tier heading is stripped from a template copy.

## Non-Goals

- Rewriting `.agent/rulebase.md` or workflows.
- Forcing every generated repo to contain every possible harness adapter file.
- Automated edits to `README.md` / `USAGE.md` unless implementation reveals explicit drift.
- Locking exact bullet wording across files beyond the four heading strings (bullets may differ slightly per harness if needed).

## Adapter files (source)

| Source path | Typical generated path |
|---|---|
| `adapters/AGENTS.md` | `AGENTS.md` |
| `adapters/CLAUDE.md` | `CLAUDE.md` (Claude harness) |
| `adapters/GEMINI.md` | `GEMINI.md` |
| `adapters/cursor-agent-system.mdc` | `.cursor/rules/agent-system.mdc` (Cursor harness) |
| `adapters/copilot-instructions.md` | `.github/copilot-instructions.md` (Copilot harness) |

## Validation contract (headings)

For any adapter file that the validator checks, the file MUST contain these **exact** level-2 heading lines (order not enforced by validator):

- `## Always do`
- `## Ask first`
- `## Never do`
- `## Commands`

Existing check preserved: if the file exists, it must still mention `.agent/` (point to canonical tree).

## Acceptance

- All five `adapters/*` files include the four headings and remain thin pointers to `.agent/`.
- `validate_template` fails if any source adapter is missing a heading.
- `validate_generated` applies tier-headings only to adapter paths that exist; skips absent paths without failure.
- `scripts/agent-validate.sh`, full unittest slice for validator, `scripts/agent-evals.sh --fast`, and strict plan validation pass after implementation.
