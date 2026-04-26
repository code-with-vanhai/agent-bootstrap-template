# Locked Proposal: agent-bootstrap-template `0.3.2` + `0.4.0`

**Status:** Pending human review — checklist resolution required before PR 1
**Date:** 2026-04-26 (revision 5)
**Driver:** BrainMap virtual scrolling plan audit

---

## Context

BrainMap dogfooded `agent:plan` on template `0.3.0` for a virtual scrolling task. The generated plan passed `agent-validate.sh` but contained 6 defects:

1. **Grounding error.** Plan quoted `entrypoints/sidepanel/App.tsx:821` as `<main className="flex-1 h-full min-h-0 p-4 overflow-y-auto">`. Working tree actually contains `<main className="flex-1 p-4">`. The "Sole Scroll Container" fix in the plan was based on fictional code.
2. **Behavior regression silently introduced.** Plan replaced `onBack` handler that previously called `fetchNotes(page)` to refresh after note edits, but did not document the removal in any "behaviors preserved" section. Plus no cache-invalidation strategy.
3. **Test snippet not runnable.** `import { act } from 'react-dom/test-utils'` (deprecated in React 19; repo uses React 19).
4. **Test snippet not runnable.** `querySelector('button:contains("Next")')` uses jQuery selector, not valid CSS — `querySelector` throws `SyntaxError`.
5. **Mock collision.** Plan stubbed `chrome` global, overwriting the existing comprehensive mock in `__tests__/setup.ts`, breaking i18n.
6. **Self-claim violating discipline.** Plan ended with `Quality target: 9.5/10 ✅` and version history `v3.0 — Fixed P2: ...` without any verification evidence.

Root cause: template has strong guardrails for **system-level** failures (missing files, invented gates, unverified completion claims) but no enforcement for:
- **Plan grounding** (planner cites code that does not exist).
- **Plan-review grounding** (reviewer iterates on solution quality without re-reading source).
- **Self-assigned quality scores** in run artifacts.

The 0.3.x → 0.4.0 work closes those gaps without breaking customizations in already-bootstrapped repos.

---

## Release `0.3.2` — Patch Independent of 0.4.0

**Goal:** Fix the version drift between `scripts/bootstrap-request.sh:14` (`template_version="0.3.0"`) and `.claude-plugin/plugin.json` (`"version": "0.3.1"`). Generated target files are unchanged so downstream repos can adopt `0.3.2` without running a migration.

| Change | File |
|---|---|
| Bump `template_version` → `"0.3.2"` | `scripts/bootstrap-request.sh:14` |
| Bump plugin version → `0.3.2` | `.claude-plugin/plugin.json` |
| Update marketplace version | `.claude-plugin/marketplace.json` |
| Add changelog entry (template repo, not BrainMap) | `CHANGELOG.md` |
| Tag `v0.3.2` | git tag |

**Verification:** `scripts/agent-validate.sh` passes.

---

## Release `0.4.0` — Grounded Planning & Review

Three PRs depending in sequence, plus one downstream dogfood phase.

### Locked Contracts (must be agreed before PR 1 merges)

#### Contract A — Evidence Block Format

Documented using a 4-backtick outer fence so the inner triple-backticks render literally:

````md
<!-- current-code path=entrypoints/sidepanel/App.tsx lines=821-821 ref=abc1234 region_sha256=<full-hex> -->
```tsx
<main className="flex-1 p-4">
```
<!-- /current-code -->
````

**Rules:**

- `path`: repo-root-relative POSIX. No `..`, no absolute paths.
- `lines`: `A-B`, 1-indexed inclusive. Single line uses `A-A`.
- `ref`: git short SHA (≥ 7 chars) at the commit the planner read.
- `region_sha256`: SHA-256 of the **entire whitespace-normalized snippet** (collapse runs of whitespace, strip trailing). Validator may display a short prefix but always hashes full content so tampering after N characters is still detected.
- Validator parses by HTML comment boundaries, **not** by markdown fence — snippets containing triple-backtick are allowed.
- Inner fence language is free-form (tsx/ts/py/text/...) for GitHub rendering.

**Canonical documentation locations** (to ensure target repos receive it via patch, not via `core/skills/` which is feature-gated):

- `core/workflows/feature-workflow.md` — section "Grounding Requirements"
- `core/roles/planner.md` — section "Evidence Blocks"
- `core/roles/prompts/planner-subagent.md` — system prompt block

**Explicit non-goal:** do **not** create `core/skills/grounded-planning/SKILL.md`. Reasons:

- `agent-validate.sh:210-214` hard-codes skill count `= 7`; adding an 8th skill would fail the template self-validation.
- Standard bootstrap does not enable `native-skills`, so target repos do not have `core/skills/`.
- The grammar must live in files that are guaranteed to be copied or patched into `.agent/` of the target.

#### Contract B — Self-Claim Banned Patterns

Banned in plan/spec body text (validator-enforced in PR 2):

| Pattern | Reason |
|---|---|
| `Quality target:?\s*\d+(\.\d+)?\s*/\s*10` | Self-assigned score |
| `Score:?\s*\d+(\.\d+)?\s*/\s*10` | Self-assigned score |
| `^Status:\s*(Ready\|Done\|Complete\|Production-ready)\s*[✅✓]?` (line-start) | Self-claim completion |
| Bare `Ready for (implementation\|review\|merge\|production)` outside a `Verified with evidence:` block | Self-claim |

Status field whitelist:

- `Draft`
- `Proposed`
- `Verified with evidence: <gate-name> @ <UTC-timestamp> (exit=<code>)`

#### Contract C — Acceptance Criteria Verification Taxonomy

Every AC row must declare a Verification Method from this enum:

| Category | Definition |
|---|---|
| `AUTOMATED-UNIT` | Vitest/Jest/equivalent, deterministic, no real layout |
| `AUTOMATED-INTEGRATION` | Real browser/Node integration (Playwright, Puppeteer, Testcontainers) |
| `AUTOMATED-E2E` | Full user flow E2E |
| `BUILD-OUTPUT` | File/size/manifest assertion against build artifact |
| `TYPECHECK` | `tsc --noEmit` or equivalent |
| `MANUAL` | Human verification with documented residual risk |

**jsdom-layout rule:** if AC text mentions `clientHeight`, `getBoundingClientRect`, `scrollTop`, `IntersectionObserver`, or `getComputedStyle`, it must NOT be classified as `AUTOMATED-UNIT` in a jsdom-only environment. Promote to `AUTOMATED-INTEGRATION`, `AUTOMATED-E2E`, or `MANUAL` with documented residual risk.

---

## PR 1 — Protocols & Rules (no scripts, no new skill)

### Files modified

| File | Change |
|---|---|
| `core/commands/plan.md` | Add "Grounding Requirements" section referencing `feature-workflow.md` |
| `core/commands/review.md` | Add "Plan/Spec Review" section |
| `core/roles/planner.md` | Add "Evidence Blocks" + "Existing Behaviors Preserved" + "AC Verification Method" |
| `core/roles/reviewer.md` | Add "Plan/Spec Grounding Pass" |
| `core/roles/prompts/planner-subagent.md` | Embed Contract A grammar |
| `core/roles/prompts/reviewer-subagent.md` | Embed Plan Review Protocol |
| `core/workflows/feature-workflow.md` | "Grounding Requirements" + Contract A grammar (canonical location) |
| `core/workflows/review-workflow.md` | "Plan/Spec Review" with 4 passes (grounding → behavior → correctness → loop control max 3 rounds) |
| `core/rulebase.template.md` | "Status Field Whitelist" (Contract B) |
| `core/skills/verify-before-completion/SKILL.md` | Reference Contract B |
| `core/gates.template.md` | "AC Verification Taxonomy" (Contract C) |

### Plan Review Protocol content

```md
## Plan/Spec Review

When the review target is `.agent/runs/*/plan.md` or `spec.md`:

1. **Grounding pass first.** For every evidence block, re-read the cited file and verify the snippet matches exactly. Mismatch = P0 grounding defect.
2. **Behavior preservation pass.** For each modified function listed in `Existing Behaviors Preserved`, cross-check against actual source. Missing or wrong behaviors = P1 defect.
3. **Correctness pass.** Only after grounding and behavior passes, evaluate the proposed AFTER.
4. **Loop control.** If grounding defects send the plan back to the planner more than 3 rounds, escalate to a human reviewer instead of iterating.

Do not iterate on solution quality while grounding is broken — return to planner.
```

### Existing Behaviors Preserved content

```md
## Existing Behaviors Preserved

For each function/handler being modified, list current side effects with evidence-block citations. Each entry classified as:

- PRESERVED — kept identical
- INTENTIONALLY REMOVED — with reason and consumer impact
- BUG FIX — with root cause and test gap

An entry without an evidence-block citation is a P0 plan defect.
```

### PR 1 verification

```bash
scripts/agent-validate.sh             # template structural pass (skill count stays = 7)
tests/migrations/0.3.0/run.sh         # existing migration not regressed
```

No new executable fixtures; behavior eval lives in PR 2.

---

## PR 2 — Validator + Lint Pack

### 2.1 New `scripts/agent-validate-plan.sh` + `scripts/lib/validate_plan.py`

Bash entrypoint, Python implementation. **Stdlib only** — uses `unittest`, no pytest dependency.

**Inputs:**

```bash
scripts/agent-validate-plan.sh .agent/runs/<run-slug>/
scripts/agent-validate-plan.sh path/to/plan.md
scripts/agent-validate-plan.sh --strict path/to/plan.md
```

**Checks:**

| ID | Check | Severity |
|---|---|---|
| `EV-001` | Evidence block parses (path/lines/ref/region_sha256 all present) | High |
| `EV-002` | `path` is repo-root-relative, no `..`, file exists | High |
| `EV-003` | Snippet content matches working tree at `lines=A-B` (whitespace-normalized) | High |
| `EV-004` | `ref` commit exists; if the **cited region** at the current working tree differs from the **same region** at `ref`, warn `STALE`. Unrelated dirty files in the worktree are ignored. | Medium |
| `EV-005` | `region_sha256` (full SHA-256 of normalized snippet) matches | High |
| `SC-001` | No `Quality target:?\s*\d+(\.\d+)?\s*/\s*10` outside quoted blocks | High |
| `SC-002` | No `Score:?\s*\d+(\.\d+)?\s*/\s*10` outside quoted blocks | High |
| `SC-003` | Status line does not match self-claim regex (Contract B) | High |
| `SC-004` | `Ready for ...` only appears inside `Verified with evidence:` block | Medium |
| `LP-001` | No `querySelector\([^)]*:contains\(` in code blocks | High |
| `LP-002` | No `from ['"]react-dom/test-utils['"]` if repo has React ≥ 19 | High (repo-aware) |
| `LP-003` | No `vi\.stubGlobal\(['"]chrome['"]` if repo is MV3 extension | Medium (repo-aware, fails under `--strict`) |
| `SECT-001` | Non-trivial plan contains sections `Acceptance Criteria`, `Existing Behaviors Preserved`, `Verification` | High |
| `AC-001` | Every AC row has Verification Method ∈ Contract C enum | High |
| `AC-002` | jsdom-layout rule (Contract C) | High |

**Repo-awareness layer:**

```python
@dataclass
class RepoContext:
    react_version: str | None        # parsed from package.json dependencies + devDependencies
    is_mv3_extension: bool           # detected via:
                                     #   - public/manifest.json with manifest_version === 3
                                     #   - wxt.config.ts present
                                     #   - @types/chrome in package.json
                                     #   - test setup file mocks chrome.runtime
                                     # NOT via .agent/manifest.json (that is the agent manifest)
    test_setup_files: list[Path]
```

Output: GitHub-friendly annotation lines plus a summary table. High failures exit 1. Medium exit 0 unless `--strict`.

### 2.2 Validator self-tests

`scripts/lib/test_validate_plan.py` uses **stdlib `unittest`**, run by:

```bash
python3 -m unittest scripts.lib.test_validate_plan
```

No pytest dependency added.

### 2.3 Fix placeholder false-positive

| File | Diff |
|---|---|
| `scripts/agent-validate.sh:240` | `'{{[^}]*}}'` → `'{{[A-Z][A-Z0-9_]*}}'` |
| `tests/evals/bootstrap-pending-completion.sh` | Same regex fix |

Add unit fixture: file containing JSX `style={{ transform: 'translateY(0)' }}` is not flagged.

### 2.4 Behavior eval

```
tests/evals/plan-grounding.sh
tests/evals/fixtures/grounding-bad-stale-snippet/plan.md
tests/evals/fixtures/grounding-bad-fictional-line/plan.md
tests/evals/fixtures/grounding-good/plan.md
```

- Skips if `claude` CLI absent (existing pattern in `agent-evals.sh`).
- Invokes `agent:review` (review-only, no edit).
- Bad fixtures → output contains "P0" + "grounding".
- Good fixture → no grounding defect.
- Add to `agent-evals.sh:76` `fast_evals` array.

### 2.5 Distribution wiring

| File | Change |
|---|---|
| `scripts/bootstrap-request.sh` | Copy `agent-validate-plan.sh` + `lib/validate_plan.py` into target's `scripts/` during bootstrap |
| `scripts/agent-validate.sh` | Path check + `bash -n agent-validate-plan.sh` + `python3 -m py_compile lib/validate_plan.py` |
| `core/gates.template.md` | Document `agent-validate-plan.sh` as a **plan discipline command**, NOT a new gate mode (no changes to `scripts/agent-eval.sh`) |

### 2.6 No new sync flag — use ephemeral `v0.4.0` tag in test harness

`agent-sync.py` reads template content via `git_show`, `list_tag_files`, `tag_commit`, all of which derive from `v<version>`. Adding a `--to-ref` flag that bypasses tags would touch every read path and the `replace_from_git_tag` manifest update — too invasive for this release.

**Decision:** keep the production code path (`--to <version>` requires tag). Tests create an ephemeral local tag named exactly `v0.4.0` at HEAD if it does not exist, then run the production path, then delete the tag on cleanup. No code changes to `agent-sync.py` or `agent-sync.sh` for this concern.

### PR 2 verification

```bash
scripts/agent-validate.sh                                  # template + new self-checks
python3 -m unittest scripts.lib.test_validate_plan         # stdlib, no pytest
# (no --to-ref flag added; sync engine untouched)
tests/evals/plan-grounding.sh                              # skipped if no claude CLI
```

---

## PR 3 — Migration `0.3.0 → 0.4.0` and `0.3.2 → 0.4.0`

### 3.0 Schema extension (locked)

`agent-sync.py:155-169` only loads `core/migrations/<to>/migration.json` (single file) and rejects when `migration["from"] != current`. Repos bootstrapped from `0.3.2` will have `synced_to_template_version = 0.3.2` and need a different `from`. Two options were considered:

1. **Two files** in the same directory keyed by `from` — requires loader directory scan, rejected for ambiguity (which file wins if both match?).
2. **Schema v1 extension: `from_versions` array** — minimal, backward compatible.

**Locked: option 2.** Migration schema becomes:

```json
{
  "schema_version": 1,
  "version": "0.4.0",
  "from": "0.3.0",
  "from_versions": ["0.3.0", "0.3.2"],
  "to": "0.4.0",
  ...
}
```

`from` remains for backward compatibility with existing `0.3.0/migration.json` (loader treats it as a single-element list). `from_versions`, when present, takes precedence. Patch in `load_migration`:

```python
from_versions = migration.get("from_versions") or [migration.get("from")]
if current not in from_versions or migration["to"] != to_version or migration["version"] != to_version:
    raise NoPathError(...)
```

Single migration file:

```
core/migrations/0.4.0/
  migration.json            # from_versions: ["0.3.0", "0.3.2"]
  README.md
```

`migration.json` content is identical for both source versions because `0.3.0` and `0.3.2` are content-equivalent (only `bootstrap-request.sh` version string differs).

### 3.1 Migration policy by file group

| Group | Strategy | Rationale |
|---|---|---|
| `core/commands/*.md` | `safe_overwrite` (3-way) | Reference command files |
| `core/roles/prompts/*-subagent.md` | `safe_overwrite` (3-way) | System prompts |
| `scripts/agent-validate.sh` | `safe_overwrite` (3-way) | Owned by template |
| `scripts/agent-validate-plan.sh` (new) | `safe_overwrite` (creates if absent) | New file |
| `scripts/lib/validate_plan.py` (new) | `safe_overwrite` (creates if absent) | New file |
| `.agent/roles/*.md` | **patches** | Often customized |
| `.agent/workflows/*.md` | **patches** | Often customized |
| `.agent/rulebase.md` | **patches only** | Heavy customization (e.g., BrainMap "Required Checks") |
| `.agent/gates.md` | **patches only** | Heavy customization (repo-specific scripts) |

### 3.1.1 No new skill synced to downstream

- `agent-sync.py` only has a conditional generator for command-wrapper skills (per `0.3.0/migration.json`); no generic mechanism for arbitrary `core/skills/*`.
- Extending the schema/applier is out of scope for `0.4.0`.
- Therefore PR 1 does **not** create `core/skills/grounded-planning/SKILL.md` — Contract A grammar lives in workflows/roles which are patched into `.agent/`.

### 3.2 Patch list

```json
{
  "patches": [
    {
      "file": ".agent/workflows/feature-workflow.md",
      "anchor": "## Steps",
      "insert_after_first_match": "<Grounding Requirements + Contract A grammar>",
      "skip_if_contains": "## Grounding Requirements"
    },
    {
      "file": ".agent/workflows/review-workflow.md",
      "anchor": "## Steps",
      "insert_after_first_match": "<Plan/Spec Review section>",
      "skip_if_contains": "## Plan/Spec Review"
    },
    {
      "file": ".agent/roles/planner.md",
      "anchor": "## Process",
      "insert_after_first_match": "<Existing Behaviors Preserved + AC Verification>",
      "skip_if_contains": "## Existing Behaviors Preserved"
    },
    {
      "file": ".agent/roles/reviewer.md",
      "anchor": "## Process",
      "insert_after_first_match": "<Plan/Spec Grounding Pass>",
      "skip_if_contains": "## Plan/Spec Grounding Pass"
    },
    {
      "file": ".agent/rulebase.md",
      "anchor": "## Discipline Gates",
      "insert_after_first_match": "<Status Field Whitelist>",
      "skip_if_contains": "## Status Field Whitelist"
    },
    {
      "file": ".agent/gates.md",
      "anchor": "## Acceptance Criteria",
      "insert_after_first_match": "<AC Verification Taxonomy>",
      "skip_if_contains": "AC Verification Taxonomy"
    }
  ]
}
```

Each patch is idempotent via `skip_if_contains`. Re-running the migration is safe.

### 3.3 Conflict handling

- `safe_overwrite`: existing 3-way logic at `agent-sync.py:283-293` — exit 20, no writes.
- `patches`: anchor must match exactly once (`agent-sync.py:312-313`). Missing → conflict, no writes.
- **Optional improvement (defer to phase 4 if scope creeps):** emit `.agent/migration-conflicts.md` listing ALL conflicts before aborting, instead of aborting on first.

### 3.4 Manifest updates

```json
{
  "manifest_updates": {
    "replace": {
      "template_version": "0.4.0",
      "synced_to_template_version": "0.4.0"
    },
    "replace_from_git_tag": {
      "synced_to_template_commit": "0.4.0"
    },
    "append_to_array_unique": {
      "notes": "Synced to v0.4.0: grounded planning protocol, plan-review protocol, evidence block format, agent-validate-plan.sh, AC verification taxonomy, self-claim ban."
    }
  }
}
```

### 3.5 Migration test runtime — ephemeral `v0.4.0` tag at HEAD

The test creates the exact production tag name (`v0.4.0`) locally at HEAD only if absent, runs the production sync path, and deletes the tag on cleanup. The remote is never pushed.

```bash
#!/usr/bin/env bash
set -euo pipefail

TAG="v0.4.0"
CREATED_TAG=0
if ! git rev-parse "$TAG" >/dev/null 2>&1; then
  git tag "$TAG" HEAD
  CREATED_TAG=1
fi
trap '[ "$CREATED_TAG" = "1" ] && git tag -d "$TAG" 2>/dev/null || true' EXIT

# Run migrations from each baseline using the production --to flag
for pair in "clean:0.3.0" "customized:0.3.2" "partial:0.3.0"; do
  fixture="${pair%%:*}"
  from_ver="${pair##*:}"
  workdir="/tmp/agent-sync-test-$fixture"
  rm -rf "$workdir"
  cp -r "tests/migrations/0.4.0/fixtures/before-$fixture" "$workdir"
  # Set source manifest's synced_to_template_version to $from_ver inside fixture
  scripts/agent-sync.sh \
      --template-root . \
      --target "$workdir" \
      --to 0.4.0 \
      --apply
  diff -r "$workdir" "tests/migrations/0.4.0/fixtures/after-$fixture"
done
```

If `v0.4.0` already exists (e.g., release was tagged), the test reuses it without modification. If absent, it is created at HEAD and removed on exit.

### 3.6 Migration test fixtures

```
tests/migrations/0.4.0/
  run.sh
  fixtures/
    before-clean/         # untouched 0.3.0 baseline
    before-customized/    # rulebase + gates customized (BrainMap-like)
    before-partial/       # roles customized, rulebase clean
    after-clean/
    after-customized/     # customizations preserved + sections appended
    after-partial/
```

`run.sh` diffs `after-*` exactly. Any unexpected mutation in customized sections fails the test.

### PR 3 verification

```bash
scripts/agent-validate.sh
tests/migrations/0.3.0/run.sh
tests/migrations/0.4.0/run.sh        # uses ephemeral v0.4.0 tag at HEAD if absent
scripts/agent-evals.sh --fast
```

---

## Phase 4 — Dogfood on BrainMap (post-tag, downstream PR)

**Correct sync command:**

```bash
../agent-bootstrap-template/scripts/agent-sync.sh \
    --target . \
    --to 0.4.0 \
    --apply
```

(Not `python3 ... agent-sync.py 0.4.0`.)

### Acceptance steps

1. Sync BrainMap from `0.3.0` → `0.4.0` (single `core/migrations/0.4.0/migration.json` with `from_versions` accepting both `0.3.0` and `0.3.2`).
2. Verify `.agent/rulebase.md` "BrainMap Extension Required Checks" and `.agent/gates.md` "BrainMap Extension Review Requirements" are preserved byte-for-byte.
3. Run `scripts/agent-validate-plan.sh .agent/runs/2026-04-25-virtual-scrolling-recent-notes/`. **Expected fail** on the defects the validator can enforce against a legacy plan that has no evidence blocks:
   - `LP-001`: `:contains()` in test snippet.
   - `LP-002`: `react-dom/test-utils` import (React 19).
   - `LP-003`: `vi.stubGlobal('chrome', ...)` (MV3 detected).
   - `SC-001`: `Quality target: 9.5/10 ✅`.
   - `SECT-001`: missing `Existing Behaviors Preserved` section. Legacy plan uses `// BEFORE` / `// AFTER` comments, not Contract A evidence blocks, so neither evidence-block sections nor any `EV-*` checks fire.

   The grounding error itself (line 821 mismatch) is **not** detectable by the current check table because the legacy plan has no Contract A evidence block to verify. Detecting it would require an optional `LEG-001` legacy citation parser that scrapes `<file>:<line>` patterns in code comments and re-reads — deferred unless a clear ROI emerges. The new plan generated in step 4 will use Contract A and any future grounding error will be caught by `EV-002/EV-003`.
4. Run `agent:plan virtual-scrolling-recent-notes-v2` with the new protocol.
5. **Compare `.agent/runs/<new-slug>/plan.md` against `.agent/runs/2026-04-25-virtual-scrolling-recent-notes/plan.md`** (the two run artifacts, not against `.agent/commands/plan.md`). The new plan must:

   - Have evidence blocks with SHA matching the working tree.
   - Quote the actual `<main className="flex-1 p-4">` (no fictional `overflow-y-auto`).
   - Contain `Existing Behaviors Preserved` listing `onBack` refresh behavior with citation.
   - AC table classifies Verification Method correctly, not claiming `AUTOMATED-UNIT` for virtualizer behavior.
   - Pass `agent-validate-plan.sh`.

Phase 4 is the **acceptance evidence** for the 0.4.0 release.

---

## Risk register

| Risk | Mitigation |
|---|---|
| Patch anchor drift downstream | `skip_if_contains` idempotent; anchors chosen from stable headings (`## Steps`, `## Discipline Gates`, `## Process`, `## Acceptance Criteria`) |
| `region_sha256` strict on whitespace | Whitespace-normalize before hashing (collapse runs, strip trailing) |
| Validator noisy on un-migrated repos | Validator reads version using the same fallback chain as `agent-sync.py:177-182` (`synced_to_template_version` → `instantiated_from_template_version`); skips when result `< 0.4.0`. A repo bootstrapped fresh at `0.4.0` always has at least `instantiated_from_template_version` set. |
| Behavior eval flakiness | Skip-if-no-CLI; deterministic substring matching, not full-text compare |
| Repo-aware lint false-positive | Medium severity by default; require `--strict` to fail; `.agent/validate-plan.ignore` opt-out |
| Plan-review infinite loop | Hard limit 3 rounds in reviewer protocol → escalate human |
| Missing chain migration `0.3.2 → 0.4.0` | Single `core/migrations/0.4.0/migration.json` declares `from_versions: ["0.3.0", "0.3.2"]`; loader accepts both source versions through one file |
| Tests need `v0.4.0` tag before tag exists | Test harness creates the ephemeral local tag named `v0.4.0` at HEAD if absent, runs production `--to 0.4.0` path, deletes tag on cleanup. No new sync flag. |
| MV3 detection false-positive | Multi-signal: `manifest.json` v3 + `wxt.config` + `@types/chrome` + `chrome.runtime` mock — never via `.agent/manifest.json` |
| Skill count check breaks if 8th skill added | **Do not create new skill**; Contract A lives in workflows/roles |

---

## Execution order (locked)

| # | PR | Blocked by | Verification |
|---|---|---|---|
| 1 | `0.3.2` version drift fix | — | `agent-validate.sh` |
| 2 | `0.4.0` PR 1 — Protocols & Rules (no new skill) | 1 merged | `agent-validate.sh` (skill count stays 7) + manual review |
| 3 | `0.4.0` PR 2 — Validator + Lint Pack | 2 merged | `agent-validate.sh` + `unittest` + `plan-grounding.sh` |
| 4 | `0.4.0` PR 3 — Single migration with `from_versions` schema extension + 3 fixtures | 3 merged | `tests/migrations/0.4.0/run.sh` (ephemeral `v0.4.0` tag at HEAD) |
| 5 | Tag `v0.4.0` | 4 merged | All template gates green |
| 6 | Dogfood BrainMap (downstream PR, separate repo) | 5 tagged | Validator flags enforceable defects (lint, section, self-claim) on old plan; new plan passes |

---

## Diff vs prior round

| Change | Reason |
|---|---|
| **Removed** `core/skills/grounded-planning/SKILL.md` | `agent-validate.sh:210` hard-codes skill count = 7; standard bootstrap does not enable native-skills; target lacks `core/skills/` |
| Contract A grammar lives in `feature-workflow.md` + `planner.md` (canonical) | Files guaranteed to be patched into `.agent/` |
| **Replaced** two-migration-file approach with **schema v1 extension `from_versions: []`** | Loader at `agent-sync.py:155-169` is single-file by design and rejects ambiguous matches; array form is minimal, backward compatible with existing `0.3.0/migration.json` |
| **Dropped** `--to-ref` flag | `agent-sync.py` reads template via tag in multiple places (`git_show`, `list_tag_files`, `tag_commit`, `replace_from_git_tag`); test harness uses ephemeral `v0.4.0` tag at HEAD instead — zero sync engine changes |
| **Narrowed** `EV-004` to compare cited region at `ref` vs working tree | Avoid false `STALE` warnings caused by unrelated dirty files |
| **Aligned** validator version-skip with `detect_current_version` fallback | Match `agent-sync.py:177-182` (`synced_to_template_version` → `instantiated_from_template_version`); fresh-bootstrapped repos lack the former |
| **Softened** Phase 4 acceptance: removed `EV-002/EV-003` claim against legacy plan | Old plan has no Contract A evidence blocks; only enforceable defects (lint, sections, self-claim) are checked. Grounding-error detection on legacy plans deferred to optional `LEG-001` |
| **Documented** evidence block sample with 4-backtick outer fence | Avoid invisible/zero-width characters; render correctly on GitHub |
| **Fixed** Phase 4 sync command to `agent-sync.sh --target . --to 0.4.0 --apply` | Helper requires explicit flags |
| **Fixed** `region_sha256` to full SHA-256 of normalized snippet | Avoid tampering after N chars going undetected |
| **Fixed** test runner to `python3 -m unittest` (stdlib) | Pytest would be an invented dependency |
| **Fixed** MV3 detection to `manifest_version: 3` + `wxt.config` + `@types/chrome` + `chrome.runtime` mock | `.agent/manifest.json` is the agent manifest, not the Chrome manifest |
| **Fixed** Phase 4 compare target: two `.agent/runs/*/plan.md` artifacts | Not compared against `.agent/commands/plan.md` |
| **Fixed** changelog reference: template `CHANGELOG.md`, not BrainMap | Correct target repo |

---

## Pre-PR-1 checklist

- [x] Migration schema decision: extend `schema_version: 1` with optional `from_versions: []` array; `from` retained as single-version fallback. Loader patch in `agent-sync.py:155-169`.
- [x] Sync flag decision: no `--to-ref`; tests use ephemeral `v0.4.0` tag at HEAD.
- [x] Patch anchor `## Process` in `core/roles/planner.md` exists (`planner.md:58`).
- [x] Patch anchor `## Acceptance Criteria` in `core/gates.template.md` exists (verified).
- [ ] Human reviewer sign-off on this revision before PR 1 implementation begins.

When the final item is signed off, PR 1 implementation may begin.

---

## Status

**Pending human review.** Checklist resolution required before PR 1 implementation begins.
