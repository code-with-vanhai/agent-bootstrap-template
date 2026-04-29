# Plan: Candidate gates inserted as commented stubs (P1-1)

**Status:** Verified with evidence: agent-validate.sh pass, 97 unittests OK, agent-evals.sh --fast pass, strict plan validator clean
**Date:** 2026-04-29
**Ref commit:** `a62d873`
**Plan location note:** Stored under `docs/plans/bootstrap-090/p1-1-candidate-gates/` because this template repo dogfoods plans there; generated target repos should use `.agent/runs/<date>-<slug>/`.

## Goal

Insert `gate_discovery.py` candidates into the bootstrapped `scripts/agent-eval.sh` as commented stubs between deterministic per-gate markers, gated behind an opt-in `--discover-gates` bootstrap flag. Behavior at runtime stays `not_configured` for every gate; only the inline guidance in the comment changes.

## Run Artifact

`docs/plans/bootstrap-090/p1-1-candidate-gates/{spec.md,plan.md}`

## Affected Areas

- `scripts/agent-eval.template.sh` — add `# >>> AGENT-CANDIDATES gate=<name> ... <<<` and `# <<< END AGENT-CANDIDATES gate=<name> <<<` marker pairs in all 9 gate `case` arms; the gate-mode name list is the canonical one in `EXPECTED_GATE_MODES`. Pure comment lines; shell syntax unchanged.
- `scripts/lib/insert_gate_candidates.py` — new helper. Reads `target/scripts/agent-eval.sh`, calls `gate_discovery.discover(target_root)`, replaces the body between each gate's marker pair with `#   run <command>           # source: <evidence_file>::<evidence_key> (confidence=<level>)` lines. Idempotent. Errors out if any expected marker pair is missing.
- `scripts/bootstrap-request.sh` — parse `--discover-gates`; add `discover_gates="0"` flag; after `copy_scripts`, when `discover_gates="1"`, invoke `python3 "$TEMPLATE_ROOT/scripts/lib/insert_gate_candidates.py" --target "$TARGET_ROOT"`; append `"gate-candidate-discovery"` to `.agent/manifest.json` only when at least one candidate stub is inserted; extend `write_pending` with a `Gate candidate discovery:` line.
- `scripts/lib/validate_agent_system.py` — template-mode: assert all 9 marker pairs exist in `scripts/agent-eval.template.sh`. Generated-mode: assert markers exist in `scripts/agent-eval.sh` (already true after copy) and that, when manifest contains `gate-candidate-discovery`, at least one gate's body contains a `#   run ` line.
- `scripts/lib/test_insert_gate_candidates.py` — new tests: empty repo (markers stay empty), repo with `package.json` (npm/pnpm), repo with `pyproject.toml` (pytest/ruff), idempotent re-run produces byte-identical output, missing marker raises `SystemExit`.
- `scripts/lib/test_validate_agent_system.py` — extend `make_target` to accept `discover_gates: bool` and a `prepopulate` callback to drop a `package.json` before bootstrap; add tests covering bootstrap with and without `--discover-gates`.

## Owner

Implementer. Reviewer must check that `not_configured` remains the default arm for every gate (insertion never deletes that line) and that markers stay pure comments.

## Implementation Plan

1. Edit `scripts/agent-eval.template.sh`: insert the two marker comments **above** the existing `not_configured` (or above the `gitleaks` `if` block for `security`) line in each gate's `case` arm. Keep two-space indent.
2. Add `scripts/lib/insert_gate_candidates.py` with module functions `_marker_open(gate)`, `_marker_close(gate)`, `_render_lines(candidates)`, and `insert(target: Path) -> int` returning count of populated gates. Resolve `gate_discovery.discover(target)`. Reject malformed input by raising `SystemExit(2)` with a clear message naming the missing marker.
3. Update `scripts/bootstrap-request.sh`:
   - Initialize `discover_gates="0"` near other defaults.
   - Add `--discover-gates) discover_gates="1"; shift ;;` in the option parser.
   - After candidate insertion, append `gate-candidate-discovery` to `.agent/manifest.json::features_enabled` only if `scripts/agent-eval.sh` contains at least one `#   run ` stub. Do not declare the feature for an empty discovery result.
   - After `copy_scripts` in the call order, add `discover_gates_into_eval` invocation (new function) that returns 0 when flag is off; otherwise calls `python3 "$TEMPLATE_ROOT/scripts/lib/insert_gate_candidates.py" --target "$TARGET_ROOT"` and reports counts.
   - Update `usage()` to list `--discover-gates`.
   - Add `Gate candidate discovery:` line to `write_pending`.
4. Update `scripts/lib/validate_agent_system.py`:
   - Constants `GATE_CANDIDATE_MARKER_OPEN_FMT = "# >>> AGENT-CANDIDATES gate={gate} — review before promoting <<<"` and `GATE_CANDIDATE_MARKER_CLOSE_FMT = "# <<< END AGENT-CANDIDATES gate={gate} <<<"`.
   - `validate_template`: for each gate in `EXPECTED_GATE_MODES`, assert both markers appear in `scripts/agent-eval.template.sh`.
   - `validate_generated`: same markers in `scripts/agent-eval.sh`. When `manifest_has_feature(manifest, "gate-candidate-discovery")`, also call `re.search(r"#\s+run ", text)` on `scripts/agent-eval.sh` and require at least one match.
5. Add `scripts/lib/test_insert_gate_candidates.py` covering empty repo, Node, Python, idempotency, and missing-marker error.
6. Extend `scripts/lib/test_validate_agent_system.py` `make_target` and add three tests:
   - bootstrap without `--discover-gates` keeps eval markers empty;
   - bootstrap with `--discover-gates` plus a pre-dropped `package.json` populates the `fast` gate body;
   - manifest contains `gate-candidate-discovery` only when the flag is used and at least one stub is inserted.
7. Run gates listed below; convert any drift `current-code` block in this plan to `historical-code` after impl, keeping at least one stable `current-code` citation in `Existing Behaviors Preserved`.
8. Update spec/plan status to `Verified with evidence: …` once gates are green.

## Acceptance Criteria

| ID | Criterion | Verification Method | Gate |
|---|---|---|---|
| AC-1 | Bootstrap with `--discover-gates` and a fixture `package.json` (with `test` script) inserts at least one `#   run …` line between `gate=fast` markers | `AUTOMATED-UNIT` | `python3 -m unittest scripts.lib.test_validate_agent_system` |
| AC-2 | Bootstrap without `--discover-gates` leaves all marker bodies empty | `AUTOMATED-UNIT` | same |
| AC-3 | Re-running insertion on an already-populated `agent-eval.sh` yields byte-identical output | `AUTOMATED-UNIT` | `python3 -m unittest scripts.lib.test_insert_gate_candidates` |
| AC-4 | Empty target repo: every marker pair is preserved with empty body; no exception | `AUTOMATED-UNIT` | same |
| AC-5 | `not_configured` remains the runtime fallback for every gate after insertion | `AUTOMATED-UNIT` | regex assertion on bootstrapped `agent-eval.sh` |
| AC-6 | Template validator asserts all 9 marker pairs exist in `scripts/agent-eval.template.sh` | `AUTOMATED-INTEGRATION` | `scripts/agent-validate.sh` |
| AC-7 | Generated validator asserts `gate-candidate-discovery` feature implies at least one `#   run ` line in `scripts/agent-eval.sh` | `AUTOMATED-UNIT` | `python3 -m unittest scripts.lib.test_validate_agent_system` |
| AC-8 | Bootstrap with `--discover-gates` on a target with no candidates leaves markers empty, omits `gate-candidate-discovery`, and generated validation passes | `AUTOMATED-UNIT` | `python3 -m unittest scripts.lib.test_validate_agent_system` |
| AC-9 | `scripts/agent-validate.sh`, full unittests, `scripts/agent-evals.sh --fast` pass | `AUTOMATED-INTEGRATION` | listed commands |
| AC-10 | Strict plan validation passes pre-implementation | `AUTOMATED-INTEGRATION` | `scripts/agent-validate-plan.sh --force --strict docs/plans/bootstrap-090/p1-1-candidate-gates` |

## Evidence

Pre-implementation grounding at `a62d873`:

<!-- current-code path=scripts/lib/gate_discovery.py lines=363-376 ref=a62d873 region_sha256=7cdc10a594e1629ca74db4ce705925baa8369ffd7a3bea4fe9918a65cb51d98b -->
```python
def discover(root: Path) -> list[Candidate]:
    root = root.resolve()
    candidates: list[Candidate] = []
    for parser in (
        discover_node,
        discover_python,
        discover_go,
        discover_rust,
        discover_java,
        discover_task_files,
        discover_github_actions,
    ):
        candidates.extend(parser(root))
    return dedupe(candidates)
```
<!-- /current-code -->

<!-- historical-code path=scripts/bootstrap-request.sh lines=416-428 ref=a62d873 region_sha256=5e57df6353e271a4e2e372fa57fd60957378a0d95fef31bf59c55c04209ca6f7 -->
```bash
copy_scripts() {
  copy_file "$TEMPLATE_ROOT/scripts/agent-validate.sh" "$TARGET_ROOT/scripts/agent-validate.sh" "755"
  copy_file "$TEMPLATE_ROOT/scripts/agent-eval.template.sh" "$TARGET_ROOT/scripts/agent-eval.sh" "755"
  copy_file "$TEMPLATE_ROOT/scripts/agent-gate-discover.sh" "$TARGET_ROOT/scripts/agent-gate-discover.sh" "755"
  copy_file "$TEMPLATE_ROOT/scripts/agent-validate-plan.sh" "$TARGET_ROOT/scripts/agent-validate-plan.sh" "755"
  copy_file "$TEMPLATE_ROOT/scripts/lib/__init__.py" "$TARGET_ROOT/scripts/lib/__init__.py" "644"
  copy_file "$TEMPLATE_ROOT/scripts/lib/gate_discovery.py" "$TARGET_ROOT/scripts/lib/gate_discovery.py" "644"
  copy_file "$TEMPLATE_ROOT/scripts/lib/validate_agent_system.py" "$TARGET_ROOT/scripts/lib/validate_agent_system.py" "644"
  copy_file "$TEMPLATE_ROOT/scripts/lib/validate_plan.py" "$TARGET_ROOT/scripts/lib/validate_plan.py" "644"
  for plan_validation_file in "$TEMPLATE_ROOT"/scripts/lib/plan_validation/*.py; do
    copy_file "$plan_validation_file" "$TARGET_ROOT/scripts/lib/plan_validation/$(basename "$plan_validation_file")" "644"
  done
}
```
<!-- /historical-code -->

<!-- historical-code path=scripts/agent-eval.template.sh lines=34-41 ref=a62d873 region_sha256=5e4e7cb6e3a6eb11ddf88b4cfb021feaa6d0f71294b9d1ef6f61529f8e90c90c -->
```bash
  fast)
    # Replace with fast repo-wide checks.
    # Examples:
    # run npm run typecheck
    # run npm test
    # run npm run lint
    not_configured
    ;;
```
<!-- /historical-code -->

## Existing Behaviors Preserved

- `scripts/lib/gate_discovery.py:363-376` — `gate_discovery.discover()` is `PRESERVED` byte-for-byte; insertion script only consumes its output and produces stub comments. Source: see `current-code` above.
- `scripts/bootstrap-request.sh:416-428` — `copy_scripts` is `PRESERVED`; the new insertion runs in a separate function called after `copy_scripts`, so file copy order and permissions are unchanged. Source: see `current-code` above.
- `scripts/agent-eval.template.sh:34-41` — gate `fast` runtime behavior is `PRESERVED`; markers are pure comments, `not_configured` remains the runtime fallback. Source: see `current-code` above.

## Verification

Pre-implementation:

```bash
scripts/agent-validate-plan.sh --force --strict docs/plans/bootstrap-090/p1-1-candidate-gates
```

Post-implementation:

```bash
scripts/agent-validate.sh
python3 -m unittest scripts.lib.test_validate_plan scripts.lib.test_gate_discovery scripts.lib.test_validate_agent_system scripts.lib.test_insert_gate_candidates
bash scripts/agent-evals.sh --fast
scripts/agent-validate-plan.sh --force --strict docs/plans/bootstrap-090/p1-1-candidate-gates
```

## Required Gates

- Strict plan validation before implementation.
- Template + generated validator gates, fast evals, and the new insertion unit tests after implementation.

## Decision Ledger

| Decision | Chosen Behavior | Rationale | Alternatives Rejected | Caller/User Impact | Verification |
|---|---|---|---|---|---|
| Marker syntax | Pure shell comments `# >>> AGENT-CANDIDATES gate=<name> ... <<<` and `# <<< END AGENT-CANDIDATES gate=<name> <<<` | Comments cannot affect bash parsing; gate-scoped markers allow per-gate idempotent rewrites | YAML/JSON inserts in adjacent file (introduces drift) or sed-style patches (fragile) | Markers are visible in the generated file the agent will read | unit and template validate |
| Default state | Off; opt-in via `--discover-gates` | Avoids changing existing bootstrap output for users not asking for discovery | Always-on (changes default output) or per-feature-tier auto (couples discovery to features) | Existing behavior unchanged unless flag passed | unit no-flag test |
| Stub format | `#   run <command>           # source: <evidence_file>::<evidence_key> (confidence=<level>)` | Promotion is a one-token edit (delete leading `#`); source link is preserved for review | Plain `#   <command>` (drops evidence trail) | Reviewers can audit the source before promotion | unit candidate test |
| Idempotency | Re-run replaces only between markers; never appends or duplicates | Safe with `--force`; deterministic output | Append on each run (drift) | Bootstrap can be re-run without diff explosion | unit idempotency test |
| Manifest feature | Add `"gate-candidate-discovery"` to `features_enabled` only when at least one candidate stub is inserted | Keeps generated-mode validator scoped and avoids marking empty-discovery repos invalid | Always include feature when flag is passed; false positive when discovery returns no candidates | Discovery-using repos get explicit manifest evidence only when there is a candidate to review | generated validator |
| Empty-discovery fallback | Preserve marker pair with empty body when `gate_discovery.discover` returns no candidates for a gate | `not_configured` is still the runtime fallback; markers must persist so a future re-run can populate them without manual edits | Strip markers when empty (breaks idempotent re-run) or print warning per empty gate (noisy) | Repos where discovery currently finds nothing keep markers and a clean `agent-eval.sh`; later `--discover-gates` re-runs work without manual restoration | `test_empty_target_keeps_markers` |
| Insertion size and ordering | Emit one comment line per candidate, ordered by `(evidence_file, gate, command)`; no max count limit imposed | Matches `gate_discovery.dedupe()` ordering so output is stable; no truncation needed because comments cost nothing at runtime | Cap line count (would hide candidates without evidence-based reason) or randomize order (unstable diffs) | Reviewers see deterministic, complete candidate lists; diffs across re-runs only change when discovery output changes | `test_idempotent_rerun_byte_identical`, `test_node_fixture_emits_expected_count` |

## Contract Value Table

| Literal | Producer | Consumer | User-facing behavior | Test |
|---|---|---|---|---|
| `gate-candidate-discovery` | `scripts/bootstrap-request.sh::add_manifest_feature` | `scripts/lib/validate_agent_system.py::validate_generated` | Generated `agent-eval.sh` validator requires at least one populated stub | `test_generated_with_discover_gates` |
| `# >>> AGENT-CANDIDATES gate=<name> — review before promoting <<<` | `scripts/agent-eval.template.sh` | `scripts/lib/insert_gate_candidates.py` and validators | Bracketed insertion zone in generated `agent-eval.sh` | template validator + insert tests |
| `# <<< END AGENT-CANDIDATES gate=<name> <<<` | same | same | Closes the bracketed zone; missing marker raises `SystemExit(2)` | insert tests |
| `#   run <command>           # source: <evidence_file>::<evidence_key> (confidence=<level>)` | `scripts/lib/insert_gate_candidates.py` | Repository owner reading `agent-eval.sh` | Promotion is removing the leading `#` and trimming the source comment | insert tests |

## Test Delta

| Action | Test | Why | Expected |
|---|---|---|---|
| ADD | `scripts/lib/test_insert_gate_candidates.py` empty target | Markers preserved with empty bodies | exit 0, byte equal to template after marker block |
| ADD | `scripts/lib/test_insert_gate_candidates.py` Node fixture | `pnpm run test` candidate ends up under `gate=fast` body | regex `#   run pnpm run test` between fast markers |
| ADD | `scripts/lib/test_insert_gate_candidates.py` Python fixture | `python -m pytest` ends up under `gate=fast` body | regex match between fast markers |
| ADD | `scripts/lib/test_insert_gate_candidates.py` idempotency | Re-running on populated file matches previous output | `assertEqual` on file bytes |
| ADD | `scripts/lib/test_insert_gate_candidates.py` missing marker | Tampered file raises `SystemExit(2)` | `assertRaises(SystemExit)` |
| ADD | `scripts/lib/test_validate_agent_system.py::test_bootstrap_no_discover_keeps_markers_empty` | Bootstrap without flag does not populate stubs | regex confirms markers exist; no `#   run ` lines between them |
| ADD | `scripts/lib/test_validate_agent_system.py::test_bootstrap_discover_gates_inserts_node_candidate` | Bootstrap with flag plus pre-dropped `package.json` populates fast gate | regex match for `#   run` line in fast block |
| ADD | `scripts/lib/test_validate_agent_system.py::test_bootstrap_with_discover_gates_empty_target_omits_feature` | Empty discovery should not make generated validation fail | no `gate-candidate-discovery`, validator exit 0 |
| KEEP | `scripts/lib/test_gate_discovery.py` | gate_discovery is `PRESERVED` and still passes | unchanged |

## Risks

- **Risk:** Marker comments could be deleted by repo owners. **Mitigation:** insertion script raises `SystemExit(2)` with the missing marker name; user can re-run bootstrap with `--force --discover-gates` to restore.
- **Risk:** Discovered command could be unsafe (e.g. `npm run deploy`). **Mitigation:** stubs are commented-out and labelled with source/confidence; `gate_discovery.GATE_BY_TASK_WORD` already filters non-verification words.
- **Risk:** Re-runs append duplicate stubs. **Mitigation:** insertion replaces strictly between markers; idempotency is unit-tested.
- **Risk:** Manifest drift if user adds `gate-candidate-discovery` manually but did not use the flag. **Mitigation:** validator only requires `#   run ` presence when feature is set; harmless on a manually-discovered repo.
