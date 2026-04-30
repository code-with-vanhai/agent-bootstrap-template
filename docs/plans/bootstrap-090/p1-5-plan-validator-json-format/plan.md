# Plan: Add JSON output for plan validator (P1-5)

**Status:** Verified with evidence: agent-validate.sh @ 2026-04-30T07:29:00Z (exit=0)
**Date:** 2026-04-30
**Ref commit:** `d22e029`
**Plan location note:** Stored under `docs/plans/bootstrap-090/p1-5-plan-validator-json-format/`. Generated target repos should use `.agent/runs/<date>-<slug>/`.

## Goal

Add `--format json` to `scripts/lib/plan_validation/cli.py` so plan-validation findings are machine-readable without parsing human text, while preserving current `human|github` behavior and exit code semantics.

## Run Artifact

`docs/plans/bootstrap-090/p1-5-plan-validator-json-format/{spec.md,plan.md}`

## Affected Areas

- `scripts/lib/plan_validation/cli.py` (MODIFIED) — extend format enum from `("human", "github")` to `("human", "github", "json")`, add JSON rendering branch, keep human/github rendering unchanged.
- `scripts/lib/plan_validation/models.py` (MODIFIED) — add helper serializer for `Finding` records (e.g., `to_dict()`), or equivalent local serializer in `cli.py` if model change is unnecessary.
- `scripts/lib/test_validate_plan.py` (MODIFIED) — extend `CompatibilityWrapperTest` with JSON output contract tests and exit-code parity checks.
- `scripts/agent-validate-plan.sh` (PRESERVED) — no behavior change in P1-5; remains human/github-compatible wrapper with summary parsing only for `human`.
- `docs/plans/bootstrap-090/p1-5-plan-validator-json-format/spec.md` (NEW) and `plan.md` (NEW).

## Owner

Implementer. Reviewer verifies that:
1) `human` and `github` output contracts stay stable,
2) strict/non-strict exit semantics are unchanged,
3) JSON payload shape is deterministic and test-covered.

## Implementation Plan

1. Update `scripts/lib/plan_validation/cli.py` argument parser: `--format` choices become `("human", "github", "json")`.
2. Introduce JSON renderer path in `main()`:
   - compute `high_count`, `medium_count`, and `failure_count=len(filter_for_exit(...))`,
   - include top-level metadata (`format`, `strict`, `target`, `repo_root`, `detected_signals`, `react_version`),
   - emit both flat `findings` and grouped `files` arrays.
3. Keep existing branches intact:
   - `github`: print annotation lines only.
   - `human`: per-file headings + summary footer.
4. Add finding serialization helper:
   - either `Finding.to_dict()` in `models.py` or local serializer function in `cli.py`,
   - output fields: `check_id`, `severity`, `message`, `file`, `line`.
5. Extend `scripts/lib/test_validate_plan.py`:
   - add `test_cli_json_output_contract` (shape + counts + fields),
   - add `test_cli_json_strict_exit_parity` (same findings, strict toggles exit via existing filter semantics),
   - keep existing `test_cli_human_and_github_output_contract` passing unchanged.
6. Confirm `scripts/agent-validate-plan.sh` remains unchanged in this phase; wrapper still parses summary only under human format and does not attempt JSON parsing.
7. Run gates listed below and update plan/spec status only after successful runs.

## Existing Behaviors Preserved

- `cli.py` previously restricted format enum to `human|github`; this branch logic and exit computation are preserved structurally, with `json` added as a third branch only. Citation: `historical-code path=scripts/lib/plan_validation/cli.py lines=20-33`, `historical-code path=scripts/lib/plan_validation/cli.py lines=64-85`.

<!-- historical-code path=scripts/lib/plan_validation/cli.py lines=20-33 ref=d22e029 region_sha256=99fbd2d888a6f193677ecaa5f8f95de1ec73231f8c40897bfec05f75bfc234b1 -->
```python
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate .agent/runs/<slug>/plan.md and spec.md artifacts."
    )
    parser.add_argument("target", help="Plan file or .agent/runs/<slug>/ directory")
    parser.add_argument("--strict", action="store_true", help="Treat Medium findings as failures")
    parser.add_argument("--repo-root", help="Override repo root for context detection")
    parser.add_argument("--format", choices=("human", "github"), default="human")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Validate even if the target repo has not yet synced to template >= 0.4.0",
    )
    args = parser.parse_args(argv)
```
<!-- /historical-code -->

<!-- historical-code path=scripts/lib/plan_validation/cli.py lines=64-85 ref=d22e029 region_sha256=976b2b29f1aa1549b62d68e5b276e49795bf365459ad176e72cc98cd4e140c12 -->
```python
    if args.format == "github":
        for f in all_findings:
            print(f.format_for_github())
    else:
        for plan in plan_files:
            plan_findings = [f for f in all_findings if f.file == plan.path]
            print(f"{plan.path}:")
            if not plan_findings:
                print("  (no findings)")
                continue
            for f in plan_findings:
                print(f.format_for_human())
        print()
        print(f"Summary: {high_count} High, {medium_count} Medium "
              f"(strict={args.strict}, repo_root={repo_root})")
        if repo_ctx.detected_signals:
            print(f"Repo signals: {'; '.join(repo_ctx.detected_signals)}")
        if repo_ctx.react_version:
            print(f"React version: {repo_ctx.react_version}")

    failing = filter_for_exit(all_findings, args.strict)
    return 1 if failing else 0
```
<!-- /historical-code -->

- `Finding` currently exposes human/github renderers; JSON serializer is additive and must not alter existing formatting helpers. Citation: `current-code path=scripts/lib/plan_validation/models.py lines=20-40`.

<!-- current-code path=scripts/lib/plan_validation/models.py lines=20-40 ref=d22e029 region_sha256=3fca61cb3361e6ce1105af20e5f5b235ba4a4b294149794c006a4c4fda2134b8 -->
```python
    def format_for_human(self) -> str:
        location = ""
        if self.file is not None:
            location = f"{self.file}"
            if self.line is not None:
                location += f":{self.line}"
            location = f" [{location}]"
        return f"  [{self.severity}] {self.check_id}{location}: {self.message}"

    def format_for_github(self) -> str:
        # ::error file=path,line=N::CHECK-ID severity=High message
        kind = "error" if self.severity == SEVERITY_HIGH else "warning"
        attrs = []
        if self.file is not None:
            attrs.append(f"file={self.file}")
        if self.line is not None:
            attrs.append(f"line={self.line}")
        prefix = f"::{kind}"
        if attrs:
            prefix += " " + ",".join(attrs)
        return f"{prefix}::{self.check_id} severity={self.severity} {self.message}"
```
<!-- /current-code -->

- `scripts/agent-validate-plan.sh` wrapper behavior is preserved in P1-5: it parses summary only for `human` format and keeps stream split intact (`scripts/agent-validate-plan.sh:34-44`, `scripts/agent-validate-plan.sh:99-106`).

<!-- current-code path=scripts/agent-validate-plan.sh lines=34-44 ref=d22e029 region_sha256=03c8eaf0d247637fc87cc973dc8e37e88f710453ba8cbe677bdd59bf2d73e5cb -->
```bash
format="human"
strict="false"
target_arg=""
expect_value_for=""
for arg in "$@"; do
  if [ -n "$expect_value_for" ]; then
    if [ "$expect_value_for" = "format" ]; then
      format="$arg"
    fi
    expect_value_for=""
    continue
```
<!-- /current-code -->

<!-- current-code path=scripts/agent-validate-plan.sh lines=99-106 ref=d22e029 region_sha256=8da7e6319cbc50a7287d11596a007eb8298a2d24677b48ebee79c7c41346046c -->
```bash
if [ "$format" = "human" ]; then
  summary_line="$(grep -E '^Summary: [0-9]+ High, [0-9]+ Medium' "$out_file" | tail -n 1 || true)"
  if [ -n "$summary_line" ]; then
    high_count="$(printf '%s\n' "$summary_line" | sed -E 's/^Summary: ([0-9]+) High, ([0-9]+) Medium.*/\1/')"
    medium_count="$(printf '%s\n' "$summary_line" | sed -E 's/^Summary: ([0-9]+) High, ([0-9]+) Medium.*/\2/')"
    audit_args+=(--field "high=$high_count" --field "medium=$medium_count")
  fi
fi
```
<!-- /current-code -->

- Existing compatibility test already pins human/github behavior and must remain green unchanged (`scripts/lib/test_validate_plan.py:1135-1162`).

<!-- current-code path=scripts/lib/test_validate_plan.py lines=1135-1162 ref=d22e029 region_sha256=2e494f98b13456182756ecf03ebed6faf2d6ffc87c48f3fbc98315300cb775de -->
```python
    def test_cli_human_and_github_output_contract(self):
        repo = TempRepo()
        self.addCleanup(repo.cleanup)
        plan = repo.write(".agent/runs/x/plan.md", "# Plan\n\nNo required sections.\n")
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "lib" / "validate_plan.py"),
            "--force",
            "--repo-root",
            str(repo.tmp),
            str(plan),
        ]

        human = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(human.returncode, 1)
        self.assertIn("SECT-001", human.stdout)
        self.assertIn("Summary: 1 High, 0 Medium", human.stdout)

        github = subprocess.run(
            cmd[:1] + [cmd[1], "--format", "github"] + cmd[2:],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(github.returncode, 1)
        self.assertIn("::error", github.stdout)
        self.assertIn("SECT-001 severity=High", github.stdout)
```
<!-- /current-code -->

## Existing Behaviors Changed

- `--format` enum in `cli.py` changes from 2 values to 3 values by adding `json`.
- `--format json` prints one structured JSON object to stdout instead of plain text lines.
- Tests gain explicit JSON output contract coverage and strict/non-strict exit parity under JSON format.

## Acceptance Criteria

| ID | Criterion | Verification Method | Gate |
|---|---|---|---|
| AC-1 | `python3 scripts/lib/validate_plan.py --format json --force --repo-root <repo> <target>` prints valid JSON object with `format=json`, `strict`, `target`, `repo_root`, `high_count`, `medium_count`, `failure_count`, `files`, and `findings` | `AUTOMATED-UNIT` | `python3 -m unittest scripts.lib.test_validate_plan` |
| AC-2 | JSON `findings[*]` entries include `check_id`, `severity`, `message`, `file`, `line` fields matching `Finding` values | `AUTOMATED-UNIT` | same |
| AC-3 | Exit semantics unchanged under JSON: return code equals existing `filter_for_exit(all_findings, strict)` behavior | `AUTOMATED-UNIT` | same |
| AC-4 | Existing `test_cli_human_and_github_output_contract` remains green without assertion changes | `AUTOMATED-UNIT` | same |
| AC-5 | `scripts/agent-validate-plan.sh --format human` continues emitting summary parseable as `Summary: <h> High, <m> Medium` | `AUTOMATED-INTEGRATION` | `python3 -m unittest scripts.lib.test_validate_agent_system` |
| AC-6 | `scripts/agent-validate.sh` passes after implementation | `AUTOMATED-INTEGRATION` | `bash scripts/agent-validate.sh` |
| AC-7 | Full unit test gate passes | `AUTOMATED-INTEGRATION` | `python3 -m unittest scripts.lib.test_validate_plan scripts.lib.test_gate_discovery scripts.lib.test_validate_agent_system scripts.lib.test_insert_gate_candidates scripts.lib.test_audit_log` |
| AC-8 | `scripts/agent-evals.sh --fast` passes | `AUTOMATED-INTEGRATION` | `bash scripts/agent-evals.sh --fast` |
| AC-9 | Strict plan validation passes pre-implementation | `AUTOMATED-INTEGRATION` | `scripts/agent-validate-plan.sh --force --strict docs/plans/bootstrap-090/p1-5-plan-validator-json-format` |

## Decision Ledger

| Decision | Chosen Behavior | Rationale | Alternatives Rejected | Caller/User Impact | Verification |
|---|---|---|---|---|---|
| JSON payload shape | Emit both flat `findings` and grouped `files[*].findings` arrays | Flat list is convenient for pipelines; grouped list avoids caller regroup logic and preserves parity with human per-file sections | Emit flat-only (rejected: every consumer must regroup); grouped-only (rejected: harder to stream/filter quickly) | Downstream tools can consume either style deterministically | `test_cli_json_output_contract` |
| Serializer placement | Prefer `Finding.to_dict()` in `models.py` unless it increases coupling; local helper in `cli.py` is acceptable fallback | Keeps field mapping centralized and reduces drift risk across output formats | Inline dict creation at each call site (rejected: duplication) | Stable mapping for file/line nullability | unit tests asserting exact keys/values |
| Exit semantics under json | Keep return code path unchanged (`filter_for_exit` drives exit) | JSON is output-only feature; behavior change would be surprising and risky | Special-case exit for json (rejected: breaks scripts) | Existing wrappers and CI behavior remain stable | `test_cli_json_strict_exit_parity` + existing tests |
| Wrapper interaction in P1-5 | Keep `scripts/agent-validate-plan.sh` logic unchanged; still parse summary only for human format | Limits blast radius and avoids coupling two changes (new json output + wrapper audit parsing) in one step | Update wrapper immediately to parse json (rejected for P1-5 scope) | No behavior drift for existing audit-log path | existing wrapper tests stay green |
| Count fields in JSON payload | Include `high_count`, `medium_count`, and `failure_count` as explicit integers at top level | Callers currently parse summary text for counts; explicit numeric fields remove parsing ambiguity while preserving exit semantics | Omit counts and require client recomputation from findings (rejected: duplicates logic and risks drift) | Machine consumers can branch on severity totals without re-implementing validator math | `test_cli_json_output_contract` + `test_cli_json_strict_exit_parity` |

## Contract Value Table

| Literal | Producer | Consumer | User-facing behavior | Test |
|---|---|---|---|---|
| `--format json` | `scripts/lib/plan_validation/cli.py` argparse choices | CLI callers (`scripts/agent-validate-plan.sh`, CI jobs, custom tooling) | Validator accepts machine-readable output mode | `test_cli_json_output_contract` |
| JSON key `findings` | JSON renderer in `cli.py` | Automation parsing flattened findings | Stable list of finding objects with check metadata | `test_cli_json_output_contract` |
| JSON keys `high_count` / `medium_count` / `failure_count` | JSON renderer in `cli.py` | Automation gating and dashboards | Stable numeric summary without human string parsing | `test_cli_json_output_contract`, `test_cli_json_strict_exit_parity` |

## Test Delta

| Test | Action | Why |
|---|---|---|
| `scripts.lib.test_validate_plan::CompatibilityWrapperTest::test_cli_human_and_github_output_contract` | KEEP | Guards non-regression for existing formats |
| `scripts.lib.test_validate_plan::CompatibilityWrapperTest::test_cli_json_output_contract` | ADD | New machine-readable output contract coverage |
| `scripts.lib.test_validate_plan::CompatibilityWrapperTest::test_cli_json_strict_exit_parity` | ADD | Proves json format does not alter strict/non-strict exit behavior |
| Existing P1-4 wrapper tests in `scripts.lib.test_validate_agent_system` | KEEP | Ensures human/github stream-split + audit behavior remain intact |

## Risks

- Risk: JSON payload keys drift over time and break machine consumers silently. Mitigation: assert full key-set and types in dedicated unit tests; avoid optional renames in P1-5.
- Risk: Adding serializer in `models.py` accidentally changes human/github formatting methods. Mitigation: keep formatter methods untouched and preserve existing compatibility tests.
- Risk: Wrapper or downstream scripts assume only `human|github` and reject `json` implicitly. Mitigation: P1-5 does not alter wrapper invocation defaults; JSON is opt-in.
- Risk: Order instability in `findings` or `files` arrays causes flaky tests. Mitigation: preserve current collection order from validation pass and deterministic plan-files order.

## Verification

- `scripts/agent-validate-plan.sh --force --strict docs/plans/bootstrap-090/p1-5-plan-validator-json-format`
- `bash scripts/agent-validate.sh`
- `python3 -m unittest scripts.lib.test_validate_plan scripts.lib.test_gate_discovery scripts.lib.test_validate_agent_system scripts.lib.test_insert_gate_candidates scripts.lib.test_audit_log`
- `bash scripts/agent-evals.sh --fast`
