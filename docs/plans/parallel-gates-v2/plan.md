# Stage 3 — Parallel Gate Execution (Schema v2)

Status: Implemented in 1.1.0 (commit `341f235c`)
Owner: Maintainers (agent-bootstrap-template)
Parent proposal: [`docs/2026-05-13-gate-safety-validation-improvements-proposal.md`](../../2026-05-13-gate-safety-validation-improvements-proposal.md)

## Goal

Introduce schema v2 for `gate-modes.json` with an optional
`composite_gates` block, and add a Python runner that executes composite
gates as ordered stages of parallel or serial sub-gates. Schema v1
remains accepted unchanged. The runner emits exactly one composite
`gate_run` audit event with an additive `sub_gates` array; child
`agent-eval.sh` invocations skip the per-gate audit emit when invoked by
the runner. No `.agent/gate-modes.json` is auto-created in this stage —
downstream repos opt in by writing the file themselves.

## Background and Current Code

`scripts/lib/gate_modes.py` is currently locked to `schema_version: 1`
and will raise `GateModesError` for any other value:

<!-- current-code path=scripts/lib/gate_modes.py lines=44-75 ref=341f235ccb425acd0fd60bbefd26dbe942384119 region_sha256=0a408aeb1bb67b8844df8234b26628fa9602e4471b19d4701b3cd0a755d60f44 -->
```python


class GateModesError(RuntimeError):
    """Raised when a gate-modes manifest exists but is malformed."""


def _validate_composite_gates(
    data: Mapping[str, Any], *, modes: Tuple[str, ...], source: Path
) -> dict[str, Any] | None:
    schema_version = data.get("schema_version")
    composite_gates = data.get("composite_gates")
    if schema_version == 1:
        if composite_gates is not None:
            raise GateModesError(
                f"{source}: 'composite_gates' requires schema_version 2"
            )
        return None

    if composite_gates is None:
        return None
    if not isinstance(composite_gates, dict):
        raise GateModesError(f"{source}: 'composite_gates' must be an object")

    mode_set = set(modes)
    composite_names = set(composite_gates)
    for gate_name, definition in composite_gates.items():
        if not isinstance(gate_name, str) or gate_name not in mode_set:
            raise GateModesError(
                f"{source}: composite gate {gate_name!r} must be present in 'modes'"
            )
        if not isinstance(definition, dict):
            raise GateModesError(
```
<!-- /current-code -->

The same module already documents the generated-mode fallback (use
`.agent/gate-modes.json` if present, otherwise fall back to
`DEFAULT_GATE_MODES`), which the runner reuses for the no-composite
path:

<!-- current-code path=scripts/lib/gate_modes.py lines=82-106 ref=341f235ccb425acd0fd60bbefd26dbe942384119 region_sha256=5ef1e52c507eaada8b977d15a8a953a9a99d46208cf704bc7e9c02d8d21b1bf3 -->
```python
                + ", ".join(unknown)
            )
        stages = definition.get("stages")
        if not isinstance(stages, list) or not stages:
            raise GateModesError(
                f"{source}: composite gate {gate_name!r} must define non-empty stages"
            )
        for index, stage in enumerate(stages, start=1):
            if not isinstance(stage, dict):
                raise GateModesError(
                    f"{source}: composite gate {gate_name!r} stage {index} "
                    "must be an object"
                )
            unknown_stage_keys = sorted(set(stage) - {"parallel", "serial"})
            if unknown_stage_keys:
                raise GateModesError(
                    f"{source}: composite gate {gate_name!r} stage {index} "
                    "has unknown key(s): "
                    + ", ".join(unknown_stage_keys)
                )
            if "parallel" not in stage and "serial" not in stage:
                raise GateModesError(
                    f"{source}: composite gate {gate_name!r} stage {index} "
                    "must define 'parallel' or 'serial'"
                )
```
<!-- /current-code -->

`scripts/agent-eval.template.sh` installs an EXIT trap that always
emits one `gate_run` audit event per invocation. The runner must
suppress this trap on child invocations so a composite invocation
produces exactly one composite-level event rather than one per
sub-gate:

<!-- current-code path=scripts/agent-eval.template.sh lines=25-42 ref=341f235ccb425acd0fd60bbefd26dbe942384119 region_sha256=49a32c01af0566f70dfdb9bad480b30c80ecc7320be52a4492091fbd304b132e -->
```bash
_audit_emit_gate_exit() {
  exit_code=$?
  if [ "${AGENT_EVAL_SUPPRESS_AUDIT:-0}" = "1" ]; then
    return 0
  fi
  audit_end_epoch_ms="$(_audit_epoch_ms)"
  duration_ms=$((audit_end_epoch_ms - audit_start_epoch_ms))
  if [ "$duration_ms" -lt 0 ]; then
    duration_ms=0
  fi
  if [ -x "$ROOT/scripts/agent-audit-log.sh" ]; then
    "$ROOT/scripts/agent-audit-log.sh" \
      --kind gate_run \
      --actor scripts/agent-eval.sh \
      --field "gate=$gate" \
      --field "exit_code=$exit_code" \
      --field "duration_ms=$duration_ms" || true
  fi
```
<!-- /current-code -->

The audit-log validator gates the set of allowed top-level keys and the
shape of `gate_run` payloads. The new `sub_gates` field must be added
to `ALLOWED_TOP_LEVEL_KEYS` and validated when present:

<!-- current-code path=scripts/lib/audit_log.py lines=15-46 ref=341f235ccb425acd0fd60bbefd26dbe942384119 region_sha256=6963dd06cdfc6a8b1d07a7a92a458aa48fca9173a3c6d2d85d14b2a7606d2d7a -->
```python


SCHEMA_VERSION = 1
ALLOWED_KINDS = frozenset({"gate_run", "plan_validation", "subagent_run"})
REQUIRED_PER_KIND = {
    "gate_run": ("gate", "exit_code", "duration_ms"),
    "plan_validation": ("target", "exit_code", "strict"),
    "subagent_run": ("subagent", "outcome"),
}
ALLOWED_TOP_LEVEL_KEYS = frozenset(
    {
        "v",
        "ts",
        "kind",
        "actor",
        "gate",
        "exit_code",
        "duration_ms",
        "target",
        "strict",
        "high",
        "medium",
        "subagent",
        "outcome",
        "notes",
        "extra",
        "sub_gates",
    }
)
OUTCOME_VALUES = frozenset({"complete", "aborted", "error"})
OPT_OUT_SENTINEL = ".agent/audit-log.disabled"
LOG_PATH = ".agent/audit-log.jsonl"
```
<!-- /current-code -->

The current template `core/gate-modes.json` is the canonical v1 example
this stage migrates to v2 (no composite block added in the template
itself — the v2 schema simply lifts the version constant):

<!-- current-code path=core/gate-modes.json lines=1-16 ref=341f235ccb425acd0fd60bbefd26dbe942384119 region_sha256=093e45b7a494bf1db3c3ba04b9585b551923def078757f4d3c6e374a68b3c434 -->
```json
{
  "schema_version": 2,
  "modes": [
    "changed",
    "fast",
    "frontend",
    "backend",
    "shared",
    "e2e",
    "full",
    "security",
    "release"
  ],
  "default_gate": "fast",
  "full_gate": "full"
}
```
<!-- /current-code -->

## Affected Areas

- `scripts/lib/gate_modes.py` (accept `schema_version: 2`, validate
  `composite_gates` block, cycle rules).
- `scripts/lib/test_gate_modes.py` (extend with v2 cases; keep v1
  cases green).
- New file `scripts/lib/gate_runner.py` (composite runner + CLI
  subcommands `is-composite` and `run`).
- New unit-test file `scripts/lib/test_gate_runner.py`.
- `scripts/agent-eval.template.sh` (detect composite via the runner's
  `is-composite` subcommand, `exec` the runner for composites, honour
  `AGENT_EVAL_SUPPRESS_AUDIT=1` inside the EXIT trap).
- `scripts/lib/audit_log.py` (accept optional `sub_gates` field,
  validate its shape).
- `scripts/agent-audit-log.sh` (pass through a JSON `sub_gates` field
  when provided).
- `core/gate-modes.json` (lift `schema_version` to `2`; no
  `composite_gates` block added to the template).
- `scripts/lib/bootstrap/copy_scripts.sh` (one new `copy_file` line for
  `gate_runner.py`).
- `core/migrations/<next-version>/migration.json` (delivers
  `gate_runner.py`, the updated `agent-eval.sh`, the updated
  `agent-audit-log.sh`, the updated `audit_log.py`, and the updated
  `gate_modes.py` to existing generated repos via `safe_overwrite`).

This stage touches only the local gate-running pipeline; no other
runtime boundary is involved.

## Implementation Plan

- Update `scripts/lib/gate_modes.py` so `_validate_payload` accepts
  both `schema_version: 1` and `schema_version: 2`. For v2 payloads,
  validate `composite_gates` when present: every key must be a member
  of `modes`; every mode referenced under `stages[].parallel[]` or
  `stages[].serial[]` must be a member of `modes`; reject
  self-reference and reject composite-to-composite references; reject
  empty `stages`. Expose a new `load_composite_gates(root, *, mode)`
  helper that returns the `composite_gates` mapping or `None`.
- Extend `scripts/lib/test_gate_modes.py` to keep every v1 test green
  and add v2 cases covering: valid v2 with composite definition; valid
  v2 without composite (must behave identically to v1); reject v2 with
  unknown mode reference; reject self-cycle; reject composite-to-composite
  cycle; reject empty `stages` list; reject unknown stage key (anything
  outside `parallel` and `serial`).
- Author `scripts/lib/gate_runner.py` exposing
  `load_composite(gate_name, gate_modes_path) -> CompositeGate | None`,
  `run_stage(stage, eval_script_path, root) -> list[SubGateResult]` that
  runs each entry under `parallel` concurrently via
  `concurrent.futures.ThreadPoolExecutor`, with each worker thread
  launching the child as a `subprocess.Popen` (not `subprocess.run`) so
  the runner can keep handles to live children for signal cleanup. Each
  worker calls `Popen([...], env={**os.environ, "AGENT_EVAL_SUPPRESS_AUDIT": "1"}, stdout=<tmp>, stderr=<tmp>)`,
  registers the handle in a thread-safe `_live_children` set, then
  blocks on `Popen.wait()` and removes the handle from the set before
  returning. Serial entries reuse the same `Popen` codepath, launching
  one at a time. The module also exposes
  `run_composite(composite, eval_script_path, root) -> int` which
  iterates stages in order and aggregates per the Decision Ledger row
  `composite-exit-aggregation`, an `aggregate_exit_codes(results)`
  helper, and a CLI exposing `is-composite --gate X --gate-modes Y`
  printing `yes` / `no` plus `run --gate X --gate-modes Y --eval-script Z --root R`.
- Capture per-process stdout and stderr into temporary files
  (`tempfile.NamedTemporaryFile`) via the `Popen` stdout / stderr
  kwargs and concatenate them to the parent stdout / stderr in the
  listed sub-gate order after the stage completes, so interleaved
  output never produces unreadable logs.
- Update `scripts/agent-eval.template.sh`:
  - Just after parsing `gate`, run
    `python3 "$ROOT/scripts/lib/gate_runner.py" is-composite --gate "$gate" --gate-modes "$ROOT/.agent/gate-modes.json"`
    (template uses `core/gate-modes.json`); if the helper exits `0`
    with `yes` on stdout, `exec` the runner via
    `python3 "$ROOT/scripts/lib/gate_runner.py" run --gate "$gate" --gate-modes <path> --eval-script "$0" --root "$ROOT"`.
  - Inside `_audit_emit_gate_exit`, add a guard
    `if [ "${AGENT_EVAL_SUPPRESS_AUDIT:-0}" = "1" ]; then return 0; fi`
    so child invocations launched by the runner do not emit per-sub-gate
    `gate_run` events.
- Update `scripts/lib/audit_log.py` to add `"sub_gates"` to
  `ALLOWED_TOP_LEVEL_KEYS` and validate it inside the `gate_run`
  branch: must be a JSON list of objects, each carrying
  `gate` (non-empty string), `exit_code` (int), `duration_ms`
  (non-negative int). Schema version stays `1` (additive field).
- Update `scripts/agent-audit-log.sh` so `--field sub_gates=<json>`
  parses correctly. The shell already accepts arbitrary `--field
  key=value` pairs; the runner passes the JSON string directly and the
  audit_log helper's `_coerce_field_value` already JSON-decodes values
  whose first character is `[`.
- Lift `core/gate-modes.json` to `schema_version: 2`. No composite
  block is added to the template — the template stays minimal and
  generated repos opt in by writing their own `.agent/gate-modes.json`
  when they want composite execution.
- Add `scripts/lib/gate_runner.py` to the `copy_scripts()` function in
  `scripts/lib/bootstrap/copy_scripts.sh` so new bootstraps receive
  the runner.
- Author a new migration directory `core/migrations/<next-version>/`
  whose `migration.json` lists, under `safe_overwrite`:
  `scripts/lib/gate_runner.py`,
  `scripts/agent-eval.sh`,
  `scripts/agent-audit-log.sh`,
  `scripts/lib/audit_log.py`, and
  `scripts/lib/gate_modes.py`. It sets
  `"update_tracked_files": true`. It explicitly does **not** ship a
  generated `.agent/gate-modes.json` — generated repos that want
  composite gates create the file themselves; repos that do not opt in
  continue to resolve to `DEFAULT_GATE_MODES` and the runner's
  `is-composite` helper returns `no`.

## Decision Ledger

| Decision | Chosen Behavior | Rationale | Alternatives Rejected | Caller/User Impact | Verification |
|----------|-----------------|-----------|------------------------|--------------------|--------------|
| `composite-exit-aggregation` (numeric exit-code roll-up) | Per stage, collect every sub-gate's exit code. If **every** sub-gate across the composite returned `2` (`not_configured`), the composite returns `2`. Otherwise the composite returns the worst non-`2` exit code observed; if all configured sub-gates passed, the composite returns `0`. | Prevents a composite from silently passing when no sub-gate did real work, while keeping pass-through semantics for the common case where one sub-gate is unconfigured | "Worst exit code wins, period" (composite reports `2` whenever any sub-gate is unconfigured); "Min exit code wins" (composite passes when one sub-gate passes and the rest fail) | Composite gate exit codes match the user's expectation: composite passes only when at least one sub-gate did real work and no sub-gate failed | Unit tests cover four cases: all `0`, mix of `0` and `2`, mix of failure and `2`, all `2`; assertions match the rules above |
| `composite-audit-fallback` (audit-event behavior plus `duration_ms` aggregation for child invocations) | Child `agent-eval.sh` invocations launched by the runner skip the EXIT-trap emit when `AGENT_EVAL_SUPPRESS_AUDIT=1` is set; the runner instead emits exactly one composite `gate_run` event whose `duration_ms` is the wall-clock span of the composite and whose `sub_gates` array carries one entry per child with each child's own `duration_ms` | Matches the audit consumer's "one event per user-invoked gate" contract while keeping the composite's `duration_ms` measurable and letting each child's `duration_ms` remain discoverable via the additive `sub_gates` field | Emit N+1 events (composite + per sub-gate, breaks downstream consumers expecting one event per invoked gate); drop child `duration_ms` (loses per-sub-gate debuggability) | Audit consumers see exactly one `gate_run` row per user-invoked gate; per-sub-gate `duration_ms` remains discoverable via `sub_gates[].duration_ms` | Unit test patches `subprocess.Popen` to assert child env carries `AGENT_EVAL_SUPPRESS_AUDIT=1`, asserts the composite event's `duration_ms` is non-negative, and asserts each `sub_gates[].duration_ms` is non-negative; integration smoke runs a composite and asserts `.agent/audit-log.jsonl` gains exactly one new line |
| `composite-process-harness` (concurrency primitive for parallel stages) | Run parallel sub-gates inside a `concurrent.futures.ThreadPoolExecutor`; each task launches the child as `subprocess.Popen([...], env={**os.environ, "AGENT_EVAL_SUPPRESS_AUDIT": "1"}, stdout=<tmp>, stderr=<tmp>)`, registers the handle in a thread-safe `_live_children` set, blocks on `Popen.wait()`, and then concatenates each child's captured output to the parent's stdout / stderr in listed order after the stage completes. The signal handler (see Risks) iterates `_live_children` and sends `SIGTERM` to each live handle, so `subprocess.run` (which owns its handle internally) cannot be used here. | Stdlib-only; the `Popen` handle is the same object the signal handler needs for cleanup, so the worker and signal paths agree on a single primitive; per-task temp files keep child output non-interleaved without changing the existing audit contract | `subprocess.run` (does not expose a handle the signal path can target; would require parallel bookkeeping by pid that races with `wait()`); `asyncio.create_subprocess_exec` (more code; no stdlib gain for this shape); shared stdout / stderr without capture (interleaved output is unreadable); per-task subprocess group with `os.setsid` (MVP does not need group signal forwarding) | Callers see grouped output per sub-gate in listed order; SIGINT to the runner propagates to children through the `_live_children` set | Unit test patches `subprocess.Popen` (not `subprocess.run`) to record argv and env per call, asserts parallel children launch within the same stage, asserts serial children launch one-at-a-time, and asserts SIGINT iterates `_live_children` and calls `terminate()` on each handle |

## Acceptance Criteria

| ID | Criterion | Verification Method |
|----|-----------|---------------------|
| AC-1 | A `gate-modes.json` payload with `schema_version: 2` and no `composite_gates` block behaves identically to the same payload at `schema_version: 1` (same return tuple from `load_gate_modes`) | AUTOMATED-UNIT |
| AC-2 | A v2 payload with a valid `composite_gates` block makes `load_composite_gates(...)` return the corresponding mapping, and the runner's `is-composite` CLI prints `yes` on stdout for any key in that mapping | AUTOMATED-UNIT |
| AC-3 | `gate_modes.py` rejects v2 payloads that self-reference a composite, that reference another composite, that reference a mode missing from `modes`, that contain an empty `stages` list, or that contain a stage with neither `parallel` nor `serial` | AUTOMATED-UNIT |
| AC-4 | `python3 scripts/lib/gate_runner.py run --gate X ...` exits `0` when every sub-gate exits `0`, exits `2` when every sub-gate exits `2`, and exits the worst non-`2` exit code observed otherwise | AUTOMATED-UNIT |
| AC-5 | Child `agent-eval.sh` invocations launched by the runner run with `AGENT_EVAL_SUPPRESS_AUDIT=1` in their environment, and the EXIT trap returns early so no per-sub-gate `gate_run` event reaches `.agent/audit-log.jsonl` | AUTOMATED-INTEGRATION |
| AC-6 | After a composite run, `.agent/audit-log.jsonl` contains exactly one new line whose `kind` is `gate_run`, whose `gate` matches the composite name, and whose `sub_gates` field is a JSON list containing one entry per child with `gate`, `exit_code`, `duration_ms` | AUTOMATED-INTEGRATION |
| AC-7 | `scripts/lib/audit_log.py` accepts a `gate_run` payload that carries a `sub_gates` list of well-shaped entries and rejects payloads where `sub_gates` is not a list of objects with `gate`, `exit_code`, and `duration_ms` | AUTOMATED-UNIT |
| AC-8 | The new migration's `safe_overwrite` list contains `scripts/lib/gate_runner.py`, `scripts/agent-eval.sh`, `scripts/agent-audit-log.sh`, `scripts/lib/audit_log.py`, and `scripts/lib/gate_modes.py`; it does **not** list `.agent/gate-modes.json`; `manifest_updates.update_tracked_files` is `true` | AUTOMATED-UNIT |
| AC-9 | `bash scripts/agent-validate.sh --mode template` passes after lifting `core/gate-modes.json` to `schema_version: 2` and adding the new files | AUTOMATED-INTEGRATION |

## Existing Behaviors Preserved

- `_audit_emit_gate_exit` still emits exactly one `gate_run` event per top-level `agent-eval.sh` invocation; the new `AGENT_EVAL_SUPPRESS_AUDIT` guard only skips the emit for child invocations launched by the runner (current-code `scripts/agent-eval.template.sh:25-42`, lines=25-42).
- `_validate_payload` keeps rejecting payloads with unknown / duplicate modes and with `default_gate` or `full_gate` not in `modes`; this stage only widens the allowed `schema_version` set (current-code `scripts/lib/gate_modes.py:44-75`, lines=44-75).
- `load_gate_modes(..., mode="generated")` continues to fall back to `DEFAULT_GATE_MODES` when no `.agent/gate-modes.json` is present, so generated repos that do not opt in see no behavior change (current-code `scripts/lib/gate_modes.py:82-106`, lines=82-106).
- `audit_log.py` keeps `SCHEMA_VERSION = 1` and keeps rejecting unknown top-level keys; the new `sub_gates` field is purely additive (current-code `scripts/lib/audit_log.py:15-46`, lines=15-46).
- The template `core/gate-modes.json` keeps its `modes`, `default_gate`, and `full_gate` values; only `schema_version` changes (current-code `core/gate-modes.json:1-16`, lines=1-16).

## Test Delta

| Test | Action | Why |
|------|--------|-----|
| `scripts/lib/test_gate_modes.py` | UPDATE | Extend with v2 acceptance, rejection, and cycle-detection cases; keep every existing v1 case green |
| `scripts/lib/test_gate_runner.py` | ADD | New unit-test module covering composite loading, the `is-composite` CLI, exit-code aggregation, parallel vs serial stage behaviour via `subprocess.Popen` mocks, live-child registration, and signal cleanup, child env propagation, and the single-composite-event audit emission |
| `scripts/lib/test_audit_log.py` | UPDATE | Add cases that accept and reject the new `sub_gates` field shape; keep existing acceptance and rejection cases green |
| `tests/evals/security-gate-fixture.sh` | KEEP | Existing fixture must keep passing unchanged because the security gate is a leaf, not a composite |
| `tests/migrations/<next-version>/run.sh` | ADD | Per-migration smoke that applies the new migration to a fixture repo, asserts `scripts/lib/gate_runner.py` is present, asserts `agent-eval.sh` carries the `AGENT_EVAL_SUPPRESS_AUDIT` guard, and asserts `.agent/gate-modes.json` was **not** created by the migration |

## Risks

- Concurrency under signal delivery: `Ctrl-C` while a parallel stage is in flight can leave child processes running. Mitigation: the runner installs a `signal.signal(signal.SIGINT, ...)` handler that cancels the executor's futures, iterates the `_live_children` set the workers populate (see Decision Ledger row `composite-process-harness`), and calls `Popen.terminate()` on each live handle followed by `Popen.wait(timeout=<bounded>)` before re-raising; because each worker uses `subprocess.Popen` (not `subprocess.run`), the handler can target the same handles the workers are blocking on, and unit tests cover the cancellation path with a fixture that blocks until killed via `Popen.terminate()`.
- Audit-consumer breakage from the new `sub_gates` field. Mitigation: the field is additive and `audit_log.py` keeps `SCHEMA_VERSION = 1`; consumers that ignore unknown keys continue to work, and the migration smoke asserts a v1 consumer can parse a composite event without error.
- Migration conflict on `scripts/agent-eval.sh` for repos that customised the script. Mitigation: rely on the existing `safe_overwrite` 3-way conflict detection so the migration refuses to overwrite a customised file silently; the operator must resolve the conflict and re-run `agent-sync`.
- Composite gate defined in `.agent/gate-modes.json` that references a sub-gate the local `agent-eval.sh` does not implement. Mitigation: the runner shells out to `agent-eval.sh` per sub-gate; an unknown sub-gate exits `1` via the existing `Unknown gate` branch in the template, which the aggregation rule surfaces as a composite failure rather than a silent skip.

## Verification

Run from the repo root:

```bash
python3 -m unittest scripts.lib.test_gate_modes
python3 -m unittest scripts.lib.test_gate_runner
python3 -m unittest scripts.lib.test_audit_log
bash scripts/agent-validate.sh --mode template
bash scripts/agent-evals.sh --fast
bash tests/evals/security-gate-fixture.sh
for f in tests/migrations/*/run.sh; do bash "$f"; done
```

The first three commands exercise every unit assertion across the
modules this stage touches. The fourth confirms the template
validator still passes after lifting `schema_version` to `2`. The
fifth runs the existing fast gate suite (including the gate runner's
smoke path). The sixth confirms the security gate still works as a
leaf gate untouched by this stage. The seventh re-runs every
migration smoke including the new one introduced by this stage.

## Open Questions

- Q: Should the runner support `fail_fast: true` to kill remaining
  parallel jobs on the first failure?
  - DEFERRED: explicitly listed under Phase 2 in the parent proposal.
    MVP keeps "run all, wait all, aggregate" semantics so process
    cleanup logic stays bounded.
- Q: Should the template ship a sample composite under `core/gate-modes.json`?
  - RESOLVED: no. The template stays minimal at v2 with no
    `composite_gates` block; downstream repos opt in by writing their
    own `.agent/gate-modes.json`. The proposal codifies this MVP
    scope.
- Q: What is the exact `<next-version>` slug for the migration
  directory?
  - DEFERRED: chosen at merge time by `scripts/release-prepare.sh`; the
    plan uses `<next-version>` as a placeholder.
