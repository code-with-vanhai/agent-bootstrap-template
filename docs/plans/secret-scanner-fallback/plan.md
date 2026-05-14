# Stage 1 — Redacted Secret Scanner Fallback

Status: Implemented in 1.1.0 (commit `341f235c`)
Owner: Maintainers (agent-bootstrap-template)
Parent proposal: [`docs/2026-05-13-gate-safety-validation-improvements-proposal.md`](../../2026-05-13-gate-safety-validation-improvements-proposal.md)

## Goal

Add a stdlib-only Python secret scanner that runs when `gitleaks` is not
installed, and wire it into the template `security)` gate so the gate
delivers value in the common downstream case where `gitleaks` is absent.
The scanner must never print matched secret values; gate output must
contain only `path:line [PATTERN_NAME]` finding lines.

## Background and Current Code

The template `security)` gate exits with `not_configured` (exit 2)
whenever `gitleaks` is missing. The relevant branch lives in
`scripts/agent-eval.template.sh`:

<!-- current-code path=scripts/agent-eval.template.sh lines=105-123 ref=341f235ccb425acd0fd60bbefd26dbe942384119 region_sha256=334b36121a400e11ca054e598f23995a777d976a8b8331e401964e23bf992a55 -->
```bash
    # <<< END AGENT-CANDIDATES gate=backend <<<
    not_configured
    ;;
  shared)
    # Replace with shared contract/library checks.
    # >>> AGENT-CANDIDATES gate=shared — review before promoting <<<
    # <<< END AGENT-CANDIDATES gate=shared <<<
    not_configured
    ;;
  e2e)
    # Replace with end-to-end checks.
    # >>> AGENT-CANDIDATES gate=e2e — review before promoting <<<
    # <<< END AGENT-CANDIDATES gate=e2e <<<
    not_configured
    ;;
  full)
    # Replace with full verification.
    # >>> AGENT-CANDIDATES gate=full — review before promoting <<<
    # <<< END AGENT-CANDIDATES gate=full <<<
```
<!-- /current-code -->

The existing security gate test fixture sets up a bootstrapped target
and exercises both the missing-`gitleaks` path and the mocked-`gitleaks`
path:

<!-- current-code path=tests/evals/security-gate-fixture.sh lines=14-28 ref=341f235ccb425acd0fd60bbefd26dbe942384119 region_sha256=6c698de9f5918f6a09763ecafbce0e9d4efbd9f5a661a91d31e839e1c27450e1 -->
```bash

"$ROOT/scripts/bootstrap-request.sh" \
  --harness generic \
  --features standard \
  --target "$target_dir" \
  >/dev/null 2>&1

cat >"$mock_bin/gitleaks" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [ "$1" = "dir" ] && [ "${2:-}" = "--help" ]; then
  exit 0
fi
if [ "$1" = "dir" ] && [ "${2:-}" = "--redact" ] && [ "${3:-}" = "." ]; then
  printf 'gitleaks-dir-ran\n' >"$GITLEAKS_MARKER"
```
<!-- /current-code -->

Generated repos receive their copy of `agent-eval.sh` via the bootstrap
copy step in `scripts/lib/bootstrap/copy_scripts.sh`, which is the
authoritative path for adding new files to the bootstrap copy list:

<!-- current-code path=scripts/lib/bootstrap/copy_scripts.sh lines=1-31 ref=341f235ccb425acd0fd60bbefd26dbe942384119 region_sha256=7ccbad32f9994f5d0ba1793d135710cd8097370ce5ca0bce7f48e687907a01b6 -->
```bash
# Bootstrap: scripts and Python libraries copied into the target.

copy_scripts() {
  copy_file "$TEMPLATE_ROOT/scripts/agent-validate.sh" "$TARGET_ROOT/scripts/agent-validate.sh" "755"
  copy_file "$TEMPLATE_ROOT/scripts/agent-audit-log.sh" "$TARGET_ROOT/scripts/agent-audit-log.sh" "755"
  copy_file "$TEMPLATE_ROOT/scripts/agent-eval.template.sh" "$TARGET_ROOT/scripts/agent-eval.sh" "755"
  copy_file "$TEMPLATE_ROOT/scripts/agent-gate-discover.sh" "$TARGET_ROOT/scripts/agent-gate-discover.sh" "755"
  copy_file "$TEMPLATE_ROOT/scripts/agent-lock.sh" "$TARGET_ROOT/scripts/agent-lock.sh" "755"
  copy_file "$TEMPLATE_ROOT/scripts/agent-validate-plan.sh" "$TARGET_ROOT/scripts/agent-validate-plan.sh" "755"
  copy_file "$TEMPLATE_ROOT/scripts/lib/__init__.py" "$TARGET_ROOT/scripts/lib/__init__.py" "644"
  copy_file "$TEMPLATE_ROOT/scripts/lib/agent_lock.py" "$TARGET_ROOT/scripts/lib/agent_lock.py" "644"
  copy_file "$TEMPLATE_ROOT/scripts/lib/audit_log.py" "$TARGET_ROOT/scripts/lib/audit_log.py" "644"
  copy_file "$TEMPLATE_ROOT/scripts/lib/gate_discovery.py" "$TARGET_ROOT/scripts/lib/gate_discovery.py" "644"
  copy_file "$TEMPLATE_ROOT/scripts/lib/gate_modes.py" "$TARGET_ROOT/scripts/lib/gate_modes.py" "644"
  copy_file "$TEMPLATE_ROOT/scripts/lib/gate_runner.py" "$TARGET_ROOT/scripts/lib/gate_runner.py" "644"
  copy_file "$TEMPLATE_ROOT/scripts/lib/insert_gate_candidates.py" "$TARGET_ROOT/scripts/lib/insert_gate_candidates.py" "644"
  copy_file "$TEMPLATE_ROOT/scripts/lib/secret_scan_redacted.py" "$TARGET_ROOT/scripts/lib/secret_scan_redacted.py" "644"
  copy_file "$TEMPLATE_ROOT/scripts/lib/validate_agent_system.py" "$TARGET_ROOT/scripts/lib/validate_agent_system.py" "644"
  _asv="$(find "$TEMPLATE_ROOT/scripts/lib/agent_system_validation" -maxdepth 1 -type f -name '*.py' -print | LC_ALL=C sort)"
  while IFS= read -r agent_system_validation_file; do
    [ -n "$agent_system_validation_file" ] || continue
    copy_file "$agent_system_validation_file" "$TARGET_ROOT/scripts/lib/agent_system_validation/$(basename "$agent_system_validation_file")" "644"
  done <<EOF
$_asv
EOF
  copy_file "$TEMPLATE_ROOT/scripts/lib/validate_plan.py" "$TARGET_ROOT/scripts/lib/validate_plan.py" "644"
  copy_file "$TEMPLATE_ROOT/scripts/lib/validate_mcp_config.py" "$TARGET_ROOT/scripts/lib/validate_mcp_config.py" "644"
  _pv="$(find "$TEMPLATE_ROOT/scripts/lib/plan_validation" -maxdepth 1 -type f -name '*.py' -print | LC_ALL=C sort)"
  while IFS= read -r plan_validation_file; do
    [ -n "$plan_validation_file" ] || continue
    copy_file "$plan_validation_file" "$TARGET_ROOT/scripts/lib/plan_validation/$(basename "$plan_validation_file")" "644"
```
<!-- /current-code -->

The latest migration (`1.0.0`) shows the canonical migration JSON shape
this plan must follow when delivering files to existing generated repos:

<!-- current-code path=core/migrations/1.0.0/migration.json lines=1-22 ref=341f235ccb425acd0fd60bbefd26dbe942384119 region_sha256=1d694b3d26b42cc4db8634d63fc5e544ccb2d3abc960dc79643e435efeae1767 -->
```json
{
  "schema_version": 1,
  "version": "1.0.0",
  "from_versions": ["0.12.0"],
  "to": "1.0.0",
  "safe_overwrite": [],
  "patches": [],
  "manifest_updates": {
    "replace": {
      "template_version": "1.0.0",
      "synced_to_template_version": "1.0.0"
    },
    "replace_from_git_tag": {
      "synced_to_template_commit": "1.0.0"
    },
    "append_to_array_unique": {
      "notes": "Synced to v1.0.0: one-shot tracked_files backfill (Stage 3.3) records sha256 baselines for every managed file so future hops can take the Stage 3.2 checksum fast-path."
    },
    "merge_array_unique": {},
    "update_tracked_files": true
  }
}
```
<!-- /current-code -->

## Affected Areas

- `scripts/agent-eval.template.sh` (security branch only).
- New file `scripts/lib/secret_scan_redacted.py` (stdlib-only Python
  scanner).
- New unit test file `scripts/lib/test_secret_scan_redacted.py`.
- `tests/evals/security-gate-fixture.sh` (adds a third assertion for the
  Python fallback path).
- `scripts/lib/bootstrap/copy_scripts.sh` (one new `copy_file` line).
- `core/migrations/<next-version>/migration.json` (delivers the new
  scanner and the updated `agent-eval.sh` to existing generated repos).

Affected areas live entirely on the template side of the build; no
runtime boundary other than the local shell gate is touched.

## Implementation Plan

- Add `scripts/lib/secret_scan_redacted.py` with a `main(argv)` entry
  point that walks the working tree from the given `--root`, applies a
  fixed redacted pattern catalog, and writes `FINDING: path:line
  [PATTERN_NAME]` lines to stdout. Exit `0` when clean and `1` when at
  least one finding is emitted.
- Cap per-file reads at the constant `MAX_FILE_BYTES = 1_048_576` (1
  MiB). Files larger than the cap are skipped without reading their
  contents. The cap value is recorded in the Decision Ledger row
  `secret-scan-max-file-size`.
- Skip symlinks via `os.path.islink` before opening, and exclude the
  directories named in `EXCLUDE_DIRS = ("node_modules", ".git",
  "dist", "build", "__pycache__")`. Honor a line-level allowlist
  marker matching `# agent-secret-scan:allow` or
  `<!-- agent-secret-scan:allow -->` so docs and test fixtures can name
  patterns without producing findings.
- Build all test-fixture secrets via runtime string concatenation
  (`prefix + suffix`) so neither this plan nor the scanner's own tests
  appear as findings when the scanner runs over the repo.
- Update the `security)` branch of `scripts/agent-eval.template.sh` to
  prefer `gitleaks dir --redact .` when `gitleaks dir --help` succeeds,
  preserve the existing `gitleaks detect --source .` path with
  `--redact` when only `detect` is available, and route to the new
  Python scanner when no `gitleaks` is on `PATH`. The existing
  `not_configured` branch fires only when neither tool is available.
- Extend `tests/evals/security-gate-fixture.sh` with a third assertion
  that removes `gitleaks` from `PATH` and confirms the Python scanner
  runs, exits with the expected code, and that its stdout/stderr never
  contains the literal fixture token.
- Add `scripts/lib/secret_scan_redacted.py` to the `copy_scripts()`
  function in `scripts/lib/bootstrap/copy_scripts.sh` so new bootstraps
  receive the file.
- Author a new migration directory `core/migrations/<next-version>/`
  whose `migration.json` lists `scripts/lib/secret_scan_redacted.py`
  and `scripts/agent-eval.sh` under `safe_overwrite`, sets
  `"update_tracked_files": true`, and adds a `notes` entry describing
  the redacted fallback.
- Reference the new scanner from `core/skills/no-secret-leakage/SKILL.md`
  so the skill points at the automated gate path.

## Decision Ledger

| Decision | Chosen Behavior | Rationale | Alternatives Rejected | Caller/User Impact | Verification |
|----------|-----------------|-----------|------------------------|--------------------|--------------|
| `secret-scan-max-file-size` (per-file byte limit) | Skip files larger than `MAX_FILE_BYTES = 1_048_576` bytes (1 MiB) without reading them; emit no finding for the skipped file | Bounded memory and runtime on real repos; oversized files are overwhelmingly binaries that would only produce noise | No limit (unbounded memory and runtime on lockfiles and binaries) | Caller sees fast, predictable gate runtime; very large files are intentionally not scanned, which is documented in the gate output as a skip notice | Unit test loads a `MAX_FILE_BYTES + 1` byte file containing the test prefix-plus-suffix token and asserts no finding line is produced |
| `secret-scan-fallback` (gitleaks absent) | When `gitleaks` is not on `PATH`, run the redacted Python scanner instead of returning `not_configured`. When neither is present, keep the existing `not_configured` exit (`2`). | Restores gate value for the common downstream case while preserving the audit contract for repos with neither tool installed | Always exit `not_configured` (silently disables the gate); shell-only grep fallback (leaks values into logs) | Caller now gets real findings on repos without `gitleaks`; runs that lack both `gitleaks` and `python3` are unaffected and still report `not_configured` | `tests/evals/security-gate-fixture.sh` adds a third case that scrubs `PATH` of `gitleaks`, runs the gate, and asserts the Python scanner is invoked |
| `secret-scan-fixture-harness` (test fixture construction) | Build the in-fixture demo token by string concatenation at runtime (`fake_prefix + fake_suffix`) inside a temp directory; the new test mocks the absence of `gitleaks` by setting `PATH` to a minimal directory list | Prevents the scanner from finding its own fixtures or this plan during full-repo scans; uses the same temp-dir + PATH-scrub pattern already in `tests/evals/security-gate-fixture.sh` | Literal token in fixture (self-detected); patch-time skip flag (complicates the gate contract) | Caller-visible behavior is unchanged; only the test harness setup is new | Run the fixture twice in CI — once with the mocked `gitleaks` and once with `PATH` scrubbed — and assert the fixture's stderr/stdout never contain the literal demo token |

## Acceptance Criteria

| ID | Criterion | Verification Method |
|----|-----------|---------------------|
| AC-1 | When `gitleaks` is on `PATH`, the `security)` branch invokes `gitleaks dir --redact .` (or `gitleaks detect --source . --redact` when `dir` is unsupported); exit code is whatever gitleaks returns | AUTOMATED-INTEGRATION |
| AC-2 | When `gitleaks` is not on `PATH` and `python3` is, the security gate invokes `python3 scripts/lib/secret_scan_redacted.py --root .` and exits with the scanner's exit code (`0` clean, `1` finding) | AUTOMATED-INTEGRATION |
| AC-3 | When neither `gitleaks` nor `python3` is on `PATH`, the gate exits `2` and prints the existing `not_configured` message | AUTOMATED-INTEGRATION |
| AC-4 | Scanner output for a finding contains `path:line [PATTERN_NAME]` and does not contain the matched substring; running the scanner over the template repo (including this plan document) reports zero findings | AUTOMATED-UNIT |
| AC-5 | Files larger than `MAX_FILE_BYTES = 1_048_576` bytes are skipped without being opened past the size check; symlinks are skipped; entries inside `node_modules`, `.git`, `dist`, `build`, and `__pycache__` are excluded | AUTOMATED-UNIT |
| AC-6 | A line carrying `# agent-secret-scan:allow` or `<!-- agent-secret-scan:allow -->` suppresses any finding on that exact line, and no other line | AUTOMATED-UNIT |
| AC-7 | The bootstrap copy step copies `scripts/lib/secret_scan_redacted.py` into the target repo under `scripts/lib/secret_scan_redacted.py` with mode `644` | AUTOMATED-INTEGRATION |
| AC-8 | The new migration's `safe_overwrite` list includes both `scripts/lib/secret_scan_redacted.py` and `scripts/agent-eval.sh`, and its `manifest_updates.update_tracked_files` is `true` | AUTOMATED-UNIT |

## Existing Behaviors Preserved

- The `_audit_emit_gate_exit` EXIT trap at `scripts/agent-eval.template.sh:42` (current-code, lines=42-42) still emits exactly one `gate_run` event per `agent-eval.sh` invocation; the security branch changes only the body of the `case` arm, not the trap wiring.
- `gitleaks dir` is still preferred when available, falling back to `gitleaks detect --source .` for older installations (current-code `scripts/agent-eval.template.sh:113-122`, lines=113-122).
- `not_configured` (exit `2`) continues to be the response when neither `gitleaks` nor `python3` is available, matching the contract the existing fixture asserts at `tests/evals/security-gate-fixture.sh:14-28` (current-code, lines=14-28).
- The gate-mode catalog stays at schema v1 with the same nine modes; this stage does not change `scripts/lib/gate_modes.py:26-43` (current-code, lines=26-43).

## Test Delta

| Test | Action | Why |
|------|--------|-----|
| `scripts/lib/test_secret_scan_redacted.py` | ADD | New unit tests covering pattern detection, redaction, symlink skip, byte-cap skip, exclude-dir skip, allowlist marker behavior, and self-scan-clean assertion |
| `tests/evals/security-gate-fixture.sh` | UPDATE | Adds a third case that scrubs `gitleaks` from `PATH` and asserts the Python scanner runs and never prints the literal demo token; existing two cases keep passing untouched |
| `tests/migrations/<next-version>/run.sh` | ADD | Per-migration smoke test that applies the new migration to a fixture repo, asserts the scanner file exists, asserts `agent-eval.sh` security branch contains the new fallback, and runs `bash scripts/agent-validate.sh --mode generated` against the fixture |

## Risks

- False positives on high-entropy strings that are not real secrets. Mitigation: keep the pattern catalog conservative (AWS, Slack, GitHub, generic API key prefixes), and document the `agent-secret-scan:allow` marker so downstream consumers can suppress individual lines without disabling the gate. Pattern tuning is tracked in the proposal's deferred items.
- Migration conflict on `agent-eval.sh` for repos that customized the `security)` branch. Mitigation: rely on `safe_overwrite`'s existing 3-way merge conflict detection so the migration refuses to overwrite a customized file silently; the operator must resolve the conflict and re-run `agent-sync`.
- Scanner self-detection of pattern strings inside its own source. Mitigation: build all in-fixture and in-source demo tokens by runtime string concatenation, add the allowlist marker on the few doc lines that must reference a pattern verbatim, and run the scanner over the template repo in CI to enforce zero findings on this plan and the scanner sources.

## Verification

Run from the repo root:

```bash
python3 -m unittest scripts.lib.test_secret_scan_redacted
bash tests/evals/security-gate-fixture.sh
bash scripts/agent-validate.sh --mode template
bash scripts/agent-evals.sh --fast
python3 scripts/lib/secret_scan_redacted.py --root .
```

The first command exercises every unit-test assertion in the new
suite. The second confirms all three integration paths
(gitleaks present, Python fallback, neither tool). The third proves
the template validator still passes after the security branch
rewrite and the new copy entry. The fourth runs the existing fast
gate suite. The fifth is a self-scan and must report zero findings,
confirming the redaction and allowlist-marker behavior is intact.

## Open Questions

- Q: Should the migration also patch `core/skills/no-secret-leakage/SKILL.md`
  via `safe_overwrite`, or rely on the next regular template release
  to ship the updated skill?
  - RESOLVED: `safe_overwrite` the SKILL.md update inside this stage's
    migration so the skill description and the gate behavior land
    together; the file is small and has not been customized in any
    known downstream repo.
- Q: What is the exact `<next-version>` slug for the migration
  directory?
  - DEFERRED: chosen at merge time by the release-prep script
    (`scripts/release-prepare.sh`); the plan uses `<next-version>` as
    a placeholder.
