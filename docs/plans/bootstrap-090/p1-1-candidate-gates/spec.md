# Spec: Candidate gates inserted as commented stubs (P1-1)

**Status:** Verified with evidence: agent-validate.sh pass, 97 unittests OK, agent-evals.sh --fast pass, strict plan validator clean
**Date:** 2026-04-29
**Ref commit:** `a62d873`
**Plan location note:** Stored under `docs/plans/bootstrap-090/p1-1-candidate-gates/` because this template repo dogfoods plans under `docs/plans/`. Generated target repos should use `.agent/runs/<date>-<slug>/`.
**Track:** 0.9.0 P1-1, after P0-1–P0-4 landed on `main`.

## Problem

`scripts/lib/gate_discovery.py` already finds candidate verification commands from checked-in evidence (`package.json`, `pyproject.toml`, `Makefile`, GitHub Actions, etc.) and `scripts/agent-gate-discover.sh` exposes them as JSON. The bootstrap output `scripts/agent-eval.sh`, however, ships only generic placeholder examples—real candidates are not surfaced inside the gate file the agent will edit. Bootstrapping a new repo therefore loses the discovery output between bootstrap and the agent's first read of `agent-eval.sh`.

This forces every new repo to re-discover gates manually, inflates "fill in `agent-eval.sh`" effort, and makes it more likely an agent invents commands instead of promoting a discovered one.

## Goals

- Add an opt-in bootstrap flag `--discover-gates` that, after copying `agent-eval.template.sh` to the target as `agent-eval.sh`, populates a per-gate **commented stub** block with discovery output.
- Keep the file's runtime behavior unchanged: `not_configured` remains the default action for every gate; promotion is still a deliberate human edit.
- Use bracket markers in `agent-eval.template.sh` so insertion is **idempotent** (re-running bootstrap with `--force --discover-gates` replaces, never appends).
- Record `gate-candidate-discovery` in `.agent/manifest.json::features_enabled` only when the flag is used and at least one candidate stub is inserted.
- Cover insertion behavior with unit tests (idempotency, no candidates, candidates per gate) and one bootstrap fixture.

## Non-Goals

- No automatic promotion of candidates into runnable lines (`run …`). All inserted lines stay commented.
- No change to `gate_discovery.py` discovery logic, language coverage, or output shape.
- No change to `not_configured` behavior or gate mode list (`changed/fast/frontend/backend/shared/e2e/full/security/release`).
- No edit of `.agent/gates.md` content; the agent still copies promoted commands there manually.
- No new harness adapter or skill.

## Insertion Contract

`scripts/agent-eval.template.sh` adds two marker lines per gate `case` arm, before `not_configured` (or before the `gitleaks` block for `security`):

```bash
    # >>> AGENT-CANDIDATES gate=<name> — review before promoting <<<
    # <<< END AGENT-CANDIDATES gate=<name> <<<
```

Markers are pure shell comments. They do not change runtime behavior.

`scripts/lib/insert_gate_candidates.py` runs `gate_discovery.discover(target_root)` and, for each gate found, replaces the lines **between** the matching markers in `target_root/scripts/agent-eval.sh` with one commented stub per candidate command:

```text
    #   run <command>           # source: <evidence_file>::<evidence_key> (confidence=<level>)
```

Gates with no discovered candidates retain empty marker bodies. Re-running insertion is idempotent because the script only ever rewrites between the markers.

## CLI Contract

`scripts/bootstrap-request.sh` gains:

```text
--discover-gates        Discover candidate gate commands from the target
                        repository and insert them as commented stubs in
                        scripts/agent-eval.sh. Adds gate-candidate-discovery
                        to .agent/manifest.json::features_enabled only when
                        at least one candidate stub is inserted.
                        Off by default.
```

The flag is mutually independent of `--features`/`--harness`; it works whenever `agent-eval.sh` is copied. Without the flag, `agent-eval.sh` is byte-equal to today's output **except** for the static marker comments shipped from the template.

## Validation Expectations

- Template mode validator asserts every gate `case` in `scripts/agent-eval.template.sh` has both bracket markers.
- Generated mode validator asserts that `scripts/agent-eval.sh` contains the markers (always true after copy) and is shell-syntax valid (already covered by `shell_syntax`).
- `python3 -m unittest scripts.lib.test_insert_gate_candidates` covers idempotent insertion, no-candidate gates, and at least two language fixtures.
- `python3 -m unittest scripts.lib.test_validate_agent_system` covers a `--discover-gates` bootstrap that pre-populates a fixture target with `package.json` and asserts at least one `#   run pnpm run …` (or `npm run …`) appears between markers.
- `scripts/agent-validate.sh`, `scripts/agent-evals.sh --fast`, and strict plan validator on this directory pass post-implementation.
