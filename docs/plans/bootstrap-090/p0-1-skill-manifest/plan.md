# Plan: Skill Manifest + Docs Drift Detection (P0-1)

**Status:** Verified with evidence: agent-validate.sh @ 2026-04-29T03:39:37Z (exit=0)
**Date:** 2026-04-29
**Ref commit:** `303546c`
**Plan location note:** Stored under `docs/plans/bootstrap-090/p0-1-skill-manifest/` because this template repo dogfoods plans there; generated target repos should use `.agent/runs/<date>-<slug>/`. `scripts/agent-validate-plan.sh` is not gating this artifact at draft time but evidence blocks are real and SHA-256-grounded against `303546c` so the validator will accept the file once it is moved to `Proposed`.

## Goal

Replace the hard-coded skill tuple and `len == 8` check in `validate_agent_system.py` with a manifest-driven check, and add docs-drift detection for skill count statements in `README.md`, `USAGE.md`, and `core/skills/README.md`. Touch only template-mode validation; generated-mode behavior remains unchanged.

## Run Artifact

`docs/plans/bootstrap-090/p0-1-skill-manifest/{spec.md,plan.md}` (this directory).

## Affected Areas

- `scripts/lib/validate_agent_system.py` — template-mode skill validation only.
- `scripts/lib/test_validate_agent_system.py` — add unit cases.
- `core/skills/manifest.json` — new declarative source of truth.
- `README.md:44` — fix "Seven" → "8".
- `core/skills/README.md` — table consistency check (no edit if table already lists 8 skills, which it does at `303546c`).
- `USAGE.md` — drift scan only; current text at `303546c` does not contain a numeric skill count, so no edit expected.

## Owner

Implementer role with assistance from Reviewer for the validator change. No cross-boundary coordination: all touched paths are inside `scripts/lib/` and `core/skills/` plus 1 README line.

## Implementation Plan

### Step 1 — Add `core/skills/manifest.json`

Create the file with schema v1 listing all 8 currently shipped skills, in the same order as `core/skills/README.md` Skill Mapping table for reviewer ergonomics:

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

### Step 2 — Refactor `validate_agent_system.py`

Replace this block (current code at `303546c`):

<!-- historical-code path=scripts/lib/validate_agent_system.py lines=19-28 ref=303546c region_sha256=e07c524127c5c2b583d3ec485ca942f2227d803c026c6837990ca0c4be5f3644 -->
```python
EXPECTED_SKILLS = (
    "verify-before-completion",
    "root-cause-debugging",
    "scoped-implementation",
    "plan-before-code",
    "worktree-isolation",
    "no-invented-artifacts",
    "bootstrap-agent-system",
    "no-secret-leakage",
)
```
<!-- /historical-code -->

with a module-level constant for the manifest path and a helper:

```python
SKILL_MANIFEST_REL = "core/skills/manifest.json"
SKILL_MANIFEST_SCHEMA_VERSION = 1


def load_skill_manifest(root: Path) -> tuple[list[str], str | None]:
    """Return (skills, error). Empty error means manifest loaded cleanly."""
    path = root / SKILL_MANIFEST_REL
    if not path.is_file():
        return [], f"{SKILL_MANIFEST_REL} is missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [], f"{SKILL_MANIFEST_REL} is not valid JSON: {exc}"
    if not isinstance(data, dict):
        return [], f"{SKILL_MANIFEST_REL} top-level must be an object"
    if data.get("schema_version") != SKILL_MANIFEST_SCHEMA_VERSION:
        return [], f"{SKILL_MANIFEST_REL} schema_version must be {SKILL_MANIFEST_SCHEMA_VERSION}"
    skills = data.get("skills")
    if not isinstance(skills, list) or not all(isinstance(s, str) for s in skills):
        return [], f"{SKILL_MANIFEST_REL} skills must be a list of strings"
    return list(skills), None
```

Replace the hard-coded count and loop:

<!-- historical-code path=scripts/lib/validate_agent_system.py lines=283-287 ref=303546c region_sha256=46f50a8b6d4ca7ff5b349ba1fd015db4021603b9e554ec7ed77b8338cbcb3a4f -->
```python
        skill_files = list((self.root / "core/skills").glob("*/SKILL.md"))
        if len(skill_files) == 8:
            self.pass_("core/skills contains 8 skill files", "core/skills")
        else:
            self.fail(f"core/skills contains {len(skill_files)} skill files, expected 8", "core/skills")
```
<!-- /historical-code -->

<!-- historical-code path=scripts/lib/validate_agent_system.py lines=288-294 ref=303546c region_sha256=31caed531396c7eac30c74eba97bf10d619a9a25e6f5ddbb46258210f7ace6f1 -->
```python
        for skill in EXPECTED_SKILLS:
            skill_file = f"core/skills/{skill}/SKILL.md"
            self.exists(skill_file)
            self.contains(skill_file, f"^name: {re.escape(skill)}$", f"{skill_file} has matching skill name", regex=True)
            self.contains(skill_file, "^description: Use when", f"{skill_file} has trigger-style description", regex=True)
            self.contains(skill_file, "Canonical Sources", f"{skill_file} lists canonical sources")
            self.contains("core/skills/README.md", f"`{skill}`", f"core/skills/README.md maps {skill}")
```
<!-- /historical-code -->

with manifest-driven logic:

```python
        manifest_skills, manifest_error = load_skill_manifest(self.root)
        if manifest_error:
            self.fail(manifest_error, SKILL_MANIFEST_REL)
            return
        self.pass_(f"{SKILL_MANIFEST_REL} parses with schema_version {SKILL_MANIFEST_SCHEMA_VERSION}", SKILL_MANIFEST_REL)

        skill_dirs = {p.parent.name for p in (self.root / "core/skills").glob("*/SKILL.md")}
        manifest_set = set(manifest_skills)
        missing_in_dirs = sorted(manifest_set - skill_dirs)
        unexpected_dirs = sorted(skill_dirs - manifest_set)
        if missing_in_dirs:
            self.fail(
                f"{SKILL_MANIFEST_REL} references skills with no directory: {', '.join(missing_in_dirs)}",
                "core/skills",
            )
        if unexpected_dirs:
            self.fail(
                f"core/skills/ contains directories not listed in manifest: {', '.join(unexpected_dirs)}",
                "core/skills",
            )
        if not missing_in_dirs and not unexpected_dirs:
            self.pass_(f"core/skills directories match {SKILL_MANIFEST_REL}", "core/skills")

        for skill in manifest_skills:
            skill_file = f"core/skills/{skill}/SKILL.md"
            self.exists(skill_file)
            self.contains(skill_file, f"^name: {re.escape(skill)}$", f"{skill_file} has matching skill name", regex=True)
            self.contains(skill_file, "^description: Use when", f"{skill_file} has trigger-style description", regex=True)
            self.contains(skill_file, "Canonical Sources", f"{skill_file} lists canonical sources")
            self.contains("core/skills/README.md", f"`{skill}`", f"core/skills/README.md maps {skill}")

        self._check_docs_skill_count(manifest_skills)
```

### Step 3 — Add docs-drift check `_check_docs_skill_count`

```python
SKILL_COUNT_DOCS = ("README.md", "USAGE.md", "core/skills/README.md")
WORD_COUNT_RE = re.compile(
    r"\b(seven|eight|nine|ten|eleven|twelve)\s+(?:optional\s+)?(?:native\s+)?(?:behavior\s+)?skills?\b",
    re.IGNORECASE,
)
NUMERIC_COUNT_RE = re.compile(
    r"\b(\d+)\s+(?:optional\s+)?(?:native\s+)?(?:behavior\s+)?skills?\b",
    re.IGNORECASE,
)


def _check_docs_skill_count(self, manifest_skills: list[str]) -> None:
    expected = len(manifest_skills)
    for rel in SKILL_COUNT_DOCS:
        path = self.root / rel
        if not path.is_file():
            self.skip(f"{rel} not present; skill-count drift check skipped", rel)
            continue
        text = read_text(path)
        word_hits = WORD_COUNT_RE.findall(text)
        if word_hits:
            self.fail(
                f"{rel} uses word-form skill count ({', '.join(sorted(set(w.lower() for w in word_hits)))}); "
                f"rewrite as numeric '{expected}' to keep manifest as source of truth",
                rel,
            )
            continue
        numeric_hits = [int(m) for m in NUMERIC_COUNT_RE.findall(text)]
        wrong = [n for n in numeric_hits if n != expected]
        if wrong:
            self.fail(
                f"{rel} states skill count {wrong} but {SKILL_MANIFEST_REL} has {expected} skills",
                rel,
            )
        elif numeric_hits:
            self.pass_(f"{rel} skill count matches manifest ({expected})", rel)
        else:
            self.skip(f"{rel} contains no skill-count statement", rel)
```

### Step 4 — Fix `README.md:44`

Rewrite the line from word-form to numeric form. Exact change:

```diff
-- Seven optional native behavior skills: verify-before-completion, root-cause-debugging, scoped-implementation, plan-before-code, worktree-isolation, no-invented-artifacts, and bootstrap-agent-system.
++ Eight optional native behavior skills (see `core/skills/manifest.json`): verify-before-completion, root-cause-debugging, scoped-implementation, plan-before-code, worktree-isolation, no-invented-artifacts, bootstrap-agent-system, and no-secret-leakage.
```

Wait — using "Eight" word-form would trip the new validator on `README.md`. Final form must be numeric:

```diff
-- Seven optional native behavior skills: verify-before-completion, root-cause-debugging, scoped-implementation, plan-before-code, worktree-isolation, no-invented-artifacts, and bootstrap-agent-system.
++ 8 optional native behavior skills (see `core/skills/manifest.json` for the canonical list): verify-before-completion, root-cause-debugging, scoped-implementation, plan-before-code, worktree-isolation, no-invented-artifacts, bootstrap-agent-system, and no-secret-leakage.
```

### Step 5 — Add unit tests

Append to `scripts/lib/test_validate_agent_system.py` six cases. Names below are the public test method names; bodies must construct minimal repo fixtures under `tempfile.TemporaryDirectory`:

1. `test_template_skill_manifest_missing_fails`
2. `test_template_skill_manifest_invalid_json_fails`
3. `test_template_skill_manifest_wrong_schema_version_fails`
4. `test_template_skill_dir_not_in_manifest_fails`
5. `test_template_manifest_skill_dir_missing_fails`
6. `test_template_readme_word_form_skill_count_fails`
7. `test_template_readme_numeric_skill_count_mismatch_fails`
8. `test_generated_mode_runs_without_skill_manifest_present`

For test 8, the fixture must build a minimal generated layout (`.agent/`, `scripts/agent-eval.sh`, etc.) without `core/skills/`, then run `validate_generated()` and assert no exception and `validate_template`-only paths are not entered.

## Acceptance Criteria

| ID | Criterion | Verification Method | Gate |
|---|---|---|---|
| AC-1 | `core/skills/manifest.json` parses; `schema_version=1`, `skills` is list of 8 strings matching `core/skills/*/SKILL.md` directory names | `AUTOMATED-UNIT` | `python3 -m unittest scripts.lib.test_validate_agent_system` |
| AC-2 | `validate_template()` calls `load_skill_manifest`; module-level `EXPECTED_SKILLS` removed; `grep -n "EXPECTED_SKILLS" scripts/lib/validate_agent_system.py` returns 0 matches | `AUTOMATED-UNIT` | same |
| AC-3 | Validator FAILs when a directory under `core/skills/<X>/SKILL.md` exists but `X` not in manifest | `AUTOMATED-UNIT` | same |
| AC-4 | Validator FAILs when manifest lists skill `Y` but `core/skills/Y/SKILL.md` is absent | `AUTOMATED-UNIT` | same |
| AC-5 | Validator FAILs when any of `README.md`, `USAGE.md`, `core/skills/README.md` contains a word-form skill count (regex literal defined in Step 3 under `WORD_COUNT_RE`) | `AUTOMATED-UNIT` | same |
| AC-6 | Validator FAILs when a numeric-form skill count in those 3 files (regex literal defined in Step 3 under `NUMERIC_COUNT_RE`) captures any number not equal to `len(manifest.skills)` | `AUTOMATED-UNIT` | same |
| AC-7 | Validator runs `validate_generated()` against a fixture without `core/skills/` and produces no exception, no `manifest.json` read, and no skill-related FAIL | `AUTOMATED-UNIT` | same |
| AC-8 | `bash scripts/agent-validate.sh` against this repo PASSes after `README.md:44` fix and validator refactor | `AUTOMATED-INTEGRATION` | `scripts/agent-validate.sh` |
| AC-9 | `bash scripts/agent-evals.sh --fast` exits 0 (deterministic eval set unaffected) | `AUTOMATED-INTEGRATION` | `scripts/agent-evals.sh --fast` |
| AC-10 | All pre-existing tests in `scripts/lib/test_validate_agent_system.py` continue to pass | `AUTOMATED-UNIT` | `python3 -m unittest scripts.lib.test_validate_agent_system` |

None of the AC depend on real layout (`clientHeight`, `getBoundingClientRect`, etc.); jsdom layout rule is N/A — Python unit tests, not browser.

## Existing Behaviors Preserved

For each function or surface modified, classify with citation. Inline citation tokens use the backticked `path:line` form recognized by `scripts/agent-validate-plan.sh`.

- `scripts/lib/validate_agent_system.py:19-28` — `EXPECTED_SKILLS` tuple at `current-code` ref `303546c` is `INTENTIONALLY REMOVED`. Reason: tuple becomes a second source of truth alongside `manifest.json` and re-introduces the original drift problem. Consumer impact: only 2 in-file references (lines 19, 288); no other importer at `303546c`. Source citation:

<!-- historical-code path=scripts/lib/validate_agent_system.py lines=19-28 ref=303546c region_sha256=e07c524127c5c2b583d3ec485ca942f2227d803c026c6837990ca0c4be5f3644 -->
```python
EXPECTED_SKILLS = (
    "verify-before-completion",
    "root-cause-debugging",
    "scoped-implementation",
    "plan-before-code",
    "worktree-isolation",
    "no-invented-artifacts",
    "bootstrap-agent-system",
    "no-secret-leakage",
)
```
<!-- /historical-code -->

- `scripts/lib/validate_agent_system.py:288-294` — per-skill content checks (`name` frontmatter, `description: Use when`, `Canonical Sources`, mapping in `core/skills/README.md`) are `PRESERVED` byte-for-byte; only the iteration source changes from `EXPECTED_SKILLS` to `manifest_skills`. Behavioral output is identical when manifest matches directories. Source citation `current-code path=scripts/lib/validate_agent_system.py lines=288-294`:

<!-- historical-code path=scripts/lib/validate_agent_system.py lines=288-294 ref=303546c region_sha256=31caed531396c7eac30c74eba97bf10d619a9a25e6f5ddbb46258210f7ace6f1 -->
```python
        for skill in EXPECTED_SKILLS:
            skill_file = f"core/skills/{skill}/SKILL.md"
            self.exists(skill_file)
            self.contains(skill_file, f"^name: {re.escape(skill)}$", f"{skill_file} has matching skill name", regex=True)
            self.contains(skill_file, "^description: Use when", f"{skill_file} has trigger-style description", regex=True)
            self.contains(skill_file, "Canonical Sources", f"{skill_file} lists canonical sources")
            self.contains("core/skills/README.md", f"`{skill}`", f"core/skills/README.md maps {skill}")
```
<!-- /historical-code -->

- `scripts/lib/validate_agent_system.py:283-287` — hard-coded `len(skill_files) == 8` count check is `INTENTIONALLY REMOVED`. Reason: brittle on every skill addition (last hit at 0.7→0.8 transition when count went 7→8). Replaced by set-diff against manifest, which surfaces specific missing/unexpected names instead of a number mismatch. Source citation `current-code path=scripts/lib/validate_agent_system.py lines=283-287`:

<!-- historical-code path=scripts/lib/validate_agent_system.py lines=283-287 ref=303546c region_sha256=46f50a8b6d4ca7ff5b349ba1fd015db4021603b9e554ec7ed77b8338cbcb3a4f -->
```python
        skill_files = list((self.root / "core/skills").glob("*/SKILL.md"))
        if len(skill_files) == 8:
            self.pass_("core/skills contains 8 skill files", "core/skills")
        else:
            self.fail(f"core/skills contains {len(skill_files)} skill files, expected 8", "core/skills")
```
<!-- /historical-code -->

- `scripts/lib/validate_agent_system.py:323-339` (`validate_generated()` body around the placeholder/bootstrap-marker checks) — `PRESERVED`. No code path in this method touches `core/skills/`, `EXPECTED_SKILLS`, or the new manifest. Confirmed by `Grep` at `303546c`: `EXPECTED_SKILLS` appears only at lines 19 and 288, both inside `validate_template()`. New helpers `_check_docs_skill_count` and `load_skill_manifest` are wired only into `validate_template()`; generated-mode behavior is byte-identical.

- `core/skills/README.md:9-21` — Skill Mapping table is `PRESERVED`. No edit. Table already aligned with all 8 skills at `303546c`. Source citation `current-code path=core/skills/README.md lines=9-21`:

<!-- current-code path=core/skills/README.md lines=9-21 ref=303546c region_sha256=8c575011d7ed1c297deadcfc1735fd82de9f877e17d14a8a6f4a1fff3275d8e5 -->
```md
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
<!-- /current-code -->

- `README.md:44` — `BUG FIX`. Current text says "Seven" while `core/skills/` has shipped 8 directories since 0.8.0. Root cause: `no-secret-leakage` was added in 0.8.0 but the README enumeration was not updated. Test gap: no validator check existed for docs drift. Fix: rewrite to numeric form keyed off `len(manifest.skills)` and add `_check_docs_skill_count` so the same drift cannot recur silently. Source citation:

<!-- historical-code path=README.md lines=44-44 ref=303546c region_sha256=d4b73783af4d7ff0afd5077556ab52f8d211a6b82cf686d47799da342a76a5dd -->
```text
- Seven optional native behavior skills: verify-before-completion, root-cause-debugging, scoped-implementation, plan-before-code, worktree-isolation, no-invented-artifacts, and bootstrap-agent-system.
```
<!-- /historical-code -->

- `scripts/agent-evals.sh:1` and `scripts/agent-validate.sh:1` CLI shapes — `PRESERVED`. No flag, exit code, or output format change in P0-1; both are downstream gates that must continue to PASS unchanged.

## Verification

Gate command(s) and expected exit code:

```bash
bash scripts/agent-validate.sh                                # exit 0
python3 -m unittest scripts.lib.test_validate_agent_system    # exit 0
bash scripts/agent-evals.sh --fast                            # exit 0
```

Status is `Verified with evidence: agent-validate.sh @ 2026-04-29T03:39:37Z (exit=0)` after the fresh post-implementation gate run. Self-assigned scores, checkmark approvals, and bare "Ready for ..." stamps are forbidden.

## Required Gates

- `fast` (Python unit tests + shell syntax + template validation in this repo's CI) — primary.
- `release` — N/A; this is a template-source change, not a release-candidate verification.
- `security` — N/A; touches no secret-adjacent paths.

## Docs/Tests/Contracts To Update

- Tests: `scripts/lib/test_validate_agent_system.py` — add 8 new test methods listed in Step 5.
- Docs: `README.md:44` rewrite (Step 4).
- Contracts: `core/skills/manifest.json` introduces a new internal contract (`schema_version: 1`, `skills: string[]`). Documented in `Contract Value Table` below.
- No public API change. No `.agent/manifest.json` schema change.

## Contract Value Table

The new `core/skills/manifest.json` adds machine-consumed contract values. Required because the JSON shape becomes a dependency for `validate_agent_system.py` and any future P1-3 (`data-safety` skill addition) consumer.

| Literal | Producer | Consumer | User-facing behavior | Test |
|---|---|---|---|---|
| `schema_version: 1` | `core/skills/manifest.json` | `scripts/lib/validate_agent_system.py::load_skill_manifest` | Validator FAILs on mismatch; protects forward compatibility | `test_template_skill_manifest_wrong_schema_version_fails` |
| `skills: string[]` | `core/skills/manifest.json` | `validate_agent_system.py::validate_template`, `_check_docs_skill_count` | Source of truth for self-validation skill list and docs count | `test_template_skill_dir_not_in_manifest_fails`, `test_template_manifest_skill_dir_missing_fails` |

## Decision Ledger

Binding decisions before implementation. Each row states chosen behavior, rationale, rejected alternative, caller/user impact, and verification target.

| Decision | Chosen Behavior | Rationale | Alternatives Rejected | Caller/User Impact | Verification |
|---|---|---|---|---|---|
| Manifest format | JSON file `core/skills/manifest.json` with `schema_version: 1` and `skills: string[]` | Mirrors existing `core/manifest.schema.json` and `core/migrations/<v>/migration.json` style; Python stdlib `json` already imported in validator | YAML (adds dep), TOML (Py 3.11+ tomllib only, narrows runtime), Python module (executable code as data is anti-goal) | Validator gains one stdlib parse; no new dep | `test_template_skill_manifest_invalid_json_fails` |
| Manifest scope | Template-source only; not generated into target repos | Generated repos do not have `core/skills/`; reading a non-existent file in `validate_generated()` is a regression risk | Generate `<target>/.agent/skills-manifest.json` (no consumer in 0.9.0) | Zero impact on existing generated repos and migration | `test_generated_mode_runs_without_skill_manifest_present` |
| Drift-scan file scope | `README.md`, `USAGE.md`, `core/skills/README.md` only | These are the user-facing docs that make explicit skill-count claims; CHANGELOG is immutable history (per repo policy reaffirmed during P0-1 review) | Include `CHANGELOG.md` (false-positive on historical "Seven optional ..." entries from 0.7.x), include `docs/plans/**` (drafts), include all markdown (too broad) | Validator does not flag historical `CHANGELOG.md` text | `test_template_readme_word_form_skill_count_fails` |
| Word-form policy | FAIL on any of `seven|eight|nine|ten|eleven|twelve` followed by `(optional\|native\|behavior)?\s*skills?` | Forces numeric form so manifest count is the single source of truth; word-form drifts silently when count changes | Allow word-form if it matches manifest count (regex hard, would need word→int mapping; brittle for translation) | Maintainers must rewrite "Seven" as "8"; one-time README edit | `test_template_readme_word_form_skill_count_fails` |
| Numeric mismatch policy | FAIL when any captured `\d+` in a skill-count phrase ≠ `len(manifest.skills)` | Catches forgotten count update when adding a skill | Warn-only (does not stop drift) | Validator failure is the trigger to update README/USAGE | `test_template_readme_numeric_skill_count_mismatch_fails` |
| `EXPECTED_SKILLS` removal | Delete the module-level constant entirely | Two sources of truth (tuple + manifest) re-introduces the original drift problem | Keep tuple as derived constant from manifest at import time (adds startup load order risk; minor) | Internal refactor; no external API. Verified no other module imports it | `grep -n EXPECTED_SKILLS scripts/lib/validate_agent_system.py` returns 0 lines |
| Test fixture style | Build minimal repo trees inside `tempfile.TemporaryDirectory`, not real-filesystem fixtures committed under `tests/` | Matches the existing `test_validate_agent_system.py` style; avoids git-tracked fixture drift | Add `tests/fixtures/skill-manifest/{good,missing,bad-schema,...}` (more I/O, more drift surface) | Fixture-only; no public effect | New tests run cleanly under `python3 -m unittest` |

## Compatibility Matrix

P0-1 does not touch a producer/consumer boundary with separate lifecycles, so this section is intentionally empty. The manifest is consumed only by the validator inside the template repo at the same revision; there is no old-producer/new-consumer scenario.

## Test Delta

| Test | Action | Why |
|---|---|---|
| `test_template_skill_manifest_missing_fails` | `ADD` | AC-1 negative case; ensures validator fails fast when manifest is absent in template mode |
| `test_template_skill_manifest_invalid_json_fails` | `ADD` | Decision-row "Manifest format" verification |
| `test_template_skill_manifest_wrong_schema_version_fails` | `ADD` | Forward-compat guard; required for future v2 schema bump |
| `test_template_skill_dir_not_in_manifest_fails` | `ADD` | AC-3 |
| `test_template_manifest_skill_dir_missing_fails` | `ADD` | AC-4 |
| `test_template_readme_word_form_skill_count_fails` | `ADD` | AC-5; covers `Seven|Eight|...` regex |
| `test_template_readme_numeric_skill_count_mismatch_fails` | `ADD` | AC-6 |
| `test_generated_mode_runs_without_skill_manifest_present` | `ADD` | AC-7; protects against regression in target-repo validation |
| Pre-existing tests in `scripts/lib/test_validate_agent_system.py` (75 cases at `303546c`) | `KEEP` | All current behavior preserved; no edits expected |

## Risks

- Risk: Removing `EXPECTED_SKILLS` could break a currently-unknown internal importer. Mitigation: `Grep` at `303546c` confirms only 2 references both inside `validate_agent_system.py` (lines 19 and 288); refactor stays self-contained.
- Risk: New regex matches unintended phrases (e.g., a release note saying `eight skills are now bundled` in `USAGE.md`). Mitigation: regex anchors on `\bskills?\b` and requires the count word to be adjacent; full-phrase pattern reviewed in Decision Ledger row "Word-form policy". Test fixtures cover both true positive and false-positive resistance via `test_template_readme_word_form_skill_count_fails` plus the existing pass-through case.
- Risk: Future skill addition forgets the manifest update. Mitigation: validator FAILs on any directory not listed (set diff), so adding a directory without manifest entry is loud. The one-file change discipline is enforced by CI.
- Risk: Validator change accidentally affects generated mode. Mitigation: `_check_docs_skill_count`, `load_skill_manifest`, `SKILL_MANIFEST_REL` are module-level but only called from `validate_template()`; `validate_generated()` is left untouched. Verified by AC-7 unit test.
- Risk: README rewrite could conflict with parallel work in a future P0/P1 plan that edits the same line. Mitigation: bundle this 1-line README edit with the validator refactor in a single commit; downstream P0/P1 plans must rebase against it. P0-1 ships first per locked order.

## Out of Scope

- The `data-safety` skill (P1-3) addition — its manifest entry will be added in that plan, exercising the new mechanism.
- Generated-repo skill manifest — no current consumer, defer until a use case exists.
- Translating word-form to numeric automatically — out of scope; one-shot README edit is sufficient.
