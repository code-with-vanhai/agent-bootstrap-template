# Changelog

## 0.7.0 - 2026-04-28

- Added semantic `Decision Ledger` planning guidance across planner, feature workflow, review workflow, planner-subagent prompt, and the `agent:plan` command. Plans that choose fallback behavior, thresholds, matchers/classifiers, or test-harness setup now have a dedicated table for chosen behavior, rationale, rejected alternatives, caller/user impact, and verification.
- Expanded `scripts/lib/validate_plan.py` with `DEC-001`, `NUM-001`, `FALLBACK-001`, and `HARNESS-001` checks. These catch plans that leave semantic behavior decisions implicit even when grounding and conditional table checks pass.
- Added `CVT-003` and narrowed `Contract Value Table` triggering so unchanged literals and threshold constants do not force a formal contract table. CVT is now reserved for added or behavior-changed enum/status/error-code/message contract values.
- Added `core/migrations/0.7.0/` content migration from 0.6.0 to 0.7.0. The migration safe-overwrites the plan command and validator, then patches downstream planning/review docs additively.
- Bumped Claude plugin metadata, local marketplace metadata, and `scripts/bootstrap-request.sh` template version to `0.7.0`.

> **Upgrade-path note.** The 0.7.0 migration accepts `from_versions: ["0.6.0"]` only. Repos on earlier versions must sync one release at a time: 0.4.0, then 0.5.0, then 0.6.0, then 0.7.0.

> Verification status at release:
>
> - **Dogfood signal verified** against `brainmap-extension/docs/2026-04-28_chatgpt-renderer-crash-fix-plan.md`: before adding `Decision Ledger`, the new validator reported `0 High, 4 Medium` (`DEC-001`, `NUM-001`, `FALLBACK-001`, `HARNESS-001`); after revising the plan, strict validation reported `0 High, 0 Medium`.
> - **Validator unit coverage expanded** from 50 to 59 tests (`scripts/lib/test_validate_plan.py`).
> - **Deterministic gates green**: `scripts/agent-validate.sh`, `scripts/lib/test_validate_plan.py` (59/59), `scripts/agent-evals.sh --fast`, `tests/migrations/0.7.0/run.sh`.
> - **Migration contract verified** by `tests/migrations/0.7.0/run.sh`: a genuine 0.6.0 fixture syncs to 0.7.0, receives the updated planner/review/validator content, and re-apply is idempotent.

## 0.6.0 - 2026-04-28

- Strengthened plan decision-completeness discipline so generated plans bind implementers instead of leaving behavior-affecting choices open:
  - `Implementation Plan` is now a required validator section for non-trivial plans.
  - Optional `Open Questions` entries must use `- Q:` with a following `- RESOLVED:` or `- DEFERRED:` bullet. Unresolved questions are Medium in `Draft` plans and High in `Proposed` / verified plans.
  - `Implementation Plan` bullets are checked for behavior-affecting hedges such as `consider adding`, `maybe`, `could`, `or add`, and `or use`.
  - Acceptance criteria that mention codes/statuses/enums must name literal targets in backticks, and documentation/comment criteria cannot be verified by `TYPECHECK` alone.
- Added conditional plan table checks backed by a reusable `find_table_under_section(...)` parser:
  - `Contract Value Table` is required for contract literal changes and must include literal, producer, consumer, user-facing behavior, and test columns.
  - `Compatibility Matrix` is required when `Affected Areas` spans separate lifecycle boundaries, covering old producer + new consumer, new producer + old consumer, unknown value, empty value, and missing field.
  - `Test Delta` is required when a plan adds/updates/keeps tests, with action limited to `KEEP`, `UPDATE`, or `ADD`.
  - Non-empty `Risks` bullets must include `Mitigation:`.
- Expanded validator unit coverage from 37 to 50 tests, including positive/negative cases for every new check and run-directory validation with `spec.md`.
- Added `core/migrations/0.6.0/` content migration from 0.5.0 to 0.6.0. The migration updates downstream planner/workflow/validator files and patches `.agent/gates.md` additively to preserve repo-specific gate mappings.
- Bumped Claude plugin metadata, local marketplace metadata, and `scripts/bootstrap-request.sh` template version to `0.6.0`.

> **Upgrade-path note.** The 0.6.0 migration accepts `from_versions: ["0.5.0"]` only. Repos on earlier versions must sync one release at a time: 0.4.0, then 0.5.0, then 0.6.0.

> Verification status at release:
>
> - **Deterministic gates green**: `scripts/agent-validate.sh`, `scripts/lib/test_validate_plan.py` (50/50), `scripts/agent-evals.sh --fast`, `tests/migrations/0.6.0/run.sh`.
> - **Migration contract verified** by `tests/migrations/0.6.0/run.sh`: a genuine 0.5.0 fixture syncs to 0.6.0, receives the updated planner/workflow/validator content, and re-apply is idempotent.

## 0.5.0 - 2026-04-28

- Added LLM provider abstraction so eval and bootstrap tooling can target Claude Code or Codex CLI:
  - `scripts/lib/llm_provider.sh` registry with 5 functions (`llm_provider_is_known`, `llm_provider_default_bin`, `llm_provider_bin`, `llm_provider_run`, `llm_provider_is_unavailable`).
  - Per-provider invocation contracts: Claude continues to call `claude -p <prompt> [CLAUDE_EXTRA_ARGS]`; Codex calls `codex exec --skip-git-repo-check --color never --sandbox workspace-write [CODEX_EXTRA_ARGS] <prompt>` (verified against codex-cli 0.124.0).
  - New env vars: `AGENT_LLM_PROVIDER` (default `claude`), `CODEX_BIN` (default `codex`), `CODEX_EXTRA_ARGS` (default empty). Existing `CLAUDE_BIN` / `CLAUDE_EXTRA_ARGS` unchanged.
  - 49-case unit suite at `tests/lib/test_llm_provider.sh` (was 29 in 0.4.0; +20 codex-branch cases) covers env-override, bin resolution, regex match/non-match for both providers, mock-CLI argv ordering, and `CODEX_EXTRA_ARGS` placement before the prompt.
- Added `--provider <claude|codex>` flag to `scripts/agent-evals.sh` with strict precedence `--provider` > `AGENT_LLM_PROVIDER` env > default `claude`. Unknown providers fail fast with `Unknown LLM provider: <name>` and exit 2.
- Provider-aware SKIP and missing-CLI wording: `<provider> CLI not found` / `<provider> CLI unavailable (quota/auth): <line>`. Default-provider wording (`claude`) preserved byte-for-byte from 0.4.0; new wording only appears when `provider != claude`.
- Migrated 6 provider-portable evals (`verify-before-claim`, `root-cause-first`, `no-invented-gates`, `no-unrelated-changes`, `bootstrap-pending-completion`, `plan-grounding`) off Claude-specific helpers to `run_llm` / `skip_if_llm_unavailable`. The `tests/evals/test-helpers.sh::run_claude` and `skip_if_claude_unavailable` shims are retained pinned to claude for back-compat with downstream test code.
- `tests/evals/plugin-command-load.sh` continues to PASS under the default Claude provider; SKIPs cleanly with reason `plugin probe is Claude-Code-specific (provider=<x>)` when `provider != claude`. The probe is intentionally Claude-Code-specific (no Codex equivalent surface).
- Added `tests/evals/codex-harness-fixture.sh` deterministic eval (filesystem-only; no LLM CLI invoked) that asserts `bootstrap-request.sh --harness codex --features full` produces every expected `.agents/skills/agent-bootstrap/<name>/SKILL.md` for the 7 `core/skills/` entries plus 9 `core/commands/` entries. Now part of the default `--fast` deterministic set, so the set grows from 1 eval (0.4.0) to 2 evals (0.5.0); both are token-free.
- Checked-in mocks: `tests/evals/mocks/{claude-quota,claude-misaligned,codex-quota,codex-auth}.sh`. Existing `claude-quota.sh` is preserved byte-for-byte; the three new mocks complete the FAIL/SKIP coverage matrix (claude misaligned-output FAIL, codex quota SKIP, codex auth SKIP).
- Path-normalization fix in `scripts/agent-evals.sh`: relative `CLAUDE_BIN` / `CODEX_BIN` (e.g. `tests/evals/mocks/claude-quota.sh`) are normalized to absolute against the repo root before being exported to eval children. Without this, eval helpers `cd` into temp project dirs and the relative path ENOENTs even though the repo-root precheck succeeded. Bare-name bins (no slash) are left untouched so PATH lookup still works.
- Pre-existing `tests/migrations/0.4.0/run.sh` regression fix (commit `2ee1d15`): dropped the misleading `clean-from-0.3.2` scenario which faked a 0.3.2 fixture by patching only the manifest's `synced_to_template_version`, even though `git diff v0.3.0 v0.3.2 -- core/` shows ~940 lines of grounded-planning content changed. The v0.3.2 ephemeral-tag fallback now pins to the real v0.3.2 commit `499eb163` if the tag is missing locally, with a clear `git fetch --tags` hint if neither tag nor commit is reachable.
- Added `core/migrations/0.5.0/migration.json` no-op manifest. Existing 0.4.0 repos sync to 0.5.0 receiving only a manifest update plus the standard sync-log audit entry; no downstream content files are patched. New `core/migrations/0.5.0/README.md` documents the no-op contract and the upgrade path.
- Added `tests/migrations/0.5.0/run.sh` regression test covering `clean-from-0.4.0` + idempotency. Builds a genuine 0.4.0 fixture by syncing the canonical 0.3.0 baseline through 0.4.0 first (with a commit between syncs because `agent-sync.py:648-649` rejects dirty worktrees), then asserts the no-op contract: `git status --short` after `--to 0.5.0 --apply` shows EXACTLY `.agent/manifest.json` AND `.agent/sync-log.md` modified, and nothing else.
- Bumped Claude plugin metadata, local marketplace metadata, and `scripts/bootstrap-request.sh` template version to `0.5.0`.

> **Upgrade-path note for 0.3.x users.** The 0.5.0 migration accepts `from_versions: ["0.4.0"]` only. Repos still on 0.3.0 or 0.3.2 must run a two-step upgrade — `agent-sync.sh --to 0.4.0 --apply` first, then `agent-sync.sh --to 0.5.0 --apply`. Single-step `0.3.x → 0.5.0` is rejected by `agent-sync.py` with `migration metadata mismatch` (no migration walker exists by design). See `core/migrations/0.5.0/README.md`.

> Verification status at release:
>
> - **Deterministic gates green**: `scripts/agent-validate.sh`, `scripts/lib/test_validate_plan.py` (27/27), `tests/lib/test_llm_provider.sh` (49/49), `tests/migrations/0.3.0/run.sh`, `tests/migrations/0.4.0/run.sh`, `tests/migrations/0.5.0/run.sh`.
> - **Provider routing verified** end-to-end with mock CLIs (claude quota → 4 SKIP, codex quota → 4 SKIP, codex misaligned auth → SKIP, claude misaligned-output → FAIL); env precedence (`--provider` overrides `AGENT_LLM_PROVIDER`) verified.
> - **No-op migration contract verified** by `tests/migrations/0.5.0/run.sh` asserting `git status --short` post-sync shows exactly `.agent/manifest.json` + `.agent/sync-log.md`.
> - **Behavior evals (4 LLM-driven) remain advisory, NOT a release gate.** Same classification as 0.4.0; the provider abstraction does not change their flakiness profile.
> - **Default `--fast` set is deterministic and token-free** (`plugin-command-load` + `codex-harness-fixture`) — `scripts/agent-evals.sh` exits 0 cleanly on every commit / CI without Claude or Codex credentials.

## 0.4.0 - 2026-04-26

- Added grounded planning protocol enforced through plan/spec artifacts:
  - Evidence-block grammar (`<!-- current-code path lines ref region_sha256 -->`) in `core/workflows/feature-workflow.md` and `core/roles/planner.md`. Plans must re-read cited files in the same turn and quote with full SHA-256 of the whitespace-normalized snippet; fabricated "BEFORE" snippets are a P0 review defect.
  - `Existing Behaviors Preserved` requirement classifying each modified function as `PRESERVED`, `INTENTIONALLY REMOVED`, or `BUG FIX` with citation.
  - AC Verification Method enum (`AUTOMATED-UNIT`, `AUTOMATED-INTEGRATION`, `AUTOMATED-E2E`, `BUILD-OUTPUT`, `TYPECHECK`, `MANUAL`) with a jsdom layout rule that promotes layout-dependent ACs out of `AUTOMATED-UNIT`.
  - Status field whitelist in `core/rulebase.template.md`: only `Draft`, `Proposed`, or `Verified with evidence: <gate> @ <UTC> (exit=<code>)`. Self-assigned scores, ✅ checkmarks, and bare `Ready for ...` stamps are forbidden.
  - Plan/Spec Review protocol in `core/workflows/review-workflow.md` and `core/roles/reviewer.md`: grounding pass first, behavior preservation second, correctness third, with a 3-round loop limit before human escalation.
- Added `scripts/agent-validate-plan.sh` plan discipline command (NOT a gate mode) backed by `scripts/lib/validate_plan.py`, with stdlib `unittest` coverage at `scripts/lib/test_validate_plan.py`. Checks: EV-001..EV-005 (evidence integrity), SC-001..SC-004 (banned self-claims), LP-001..LP-003 (lint pack: `:contains()`, React 19 `react-dom/test-utils`, MV3 `vi.stubGlobal('chrome', ...)`), SECT-001 (required sections), AC-001/AC-002 (verification taxonomy + jsdom rule).
- Added `tests/evals/plan-grounding.sh` behavior eval with three plan fixtures (good, stale-snippet, fictional-line) wired into `agent-evals.sh` fast set.
- Added schema v1 extension `from_versions: []` in `scripts/agent-sync.py` so a single `core/migrations/0.4.0/migration.json` accepts both `0.3.0` and `0.3.2` source versions.
- Added `core/migrations/0.4.0/` migration manifest + `tests/migrations/0.4.0/run.sh` regression test (clean-from-0.3.0, clean-from-0.3.2, customized scenarios; ephemeral local `v0.3.2` and `v0.4.0` tags created if missing).
- Hardened `scripts/agent-validate.sh` placeholder regex (only `{{UPPER_CASE}}` template tokens flagged; JSX/CSS-in-JS double braces no longer false-positive) and added presence/syntax checks for the new validator files.
- Hardened `scripts/agent-evals.sh` and `tests/evals/test-helpers.sh`: detect Claude CLI quota / auth errors (e.g. `"You've hit your limit · resets ..."`, `"monthly usage limit"`, `"credit balance is too low"`, `api error 401/403/429`) and emit `SKIP` (exit 77) instead of asserting against the error string and reporting a false `FAIL`. `scripts/agent-evals.sh` now distinguishes exit codes: `0`=PASS, `77`=SKIP, other=FAIL.
- Demoted LLM-driven behavior evals out of the default `--fast` set. `scripts/agent-evals.sh` modes are now:
  - `--fast` (default): deterministic, token-free, reliable. Currently `tests/evals/plugin-command-load.sh` only. Safe to run on every commit / in CI without Claude credentials.
  - `--behavior`: LLM-driven advisory evals (`verify-before-claim`, `root-cause-first`, `no-invented-gates`, `plan-grounding`). Each run consumes Claude quota; results are advisory, NOT a release gate.
  - `--integration`: all known evals — deterministic + behavior + integration (`no-unrelated-changes`, `bootstrap-pending-completion`). Heaviest mode; only run intentionally.

  When LLM evals fail, the runner prints `LLM-driven evals are advisory; do NOT block release on this alone.` to prevent downstream consumers from misreading flaky LLM output as a release-broken signal.
- Bumped Claude plugin and local marketplace metadata to `0.4.0`. `scripts/bootstrap-request.sh` now bootstraps targets at `0.4.0`.

> Verification status at release:
>
> - **Deterministic gates green**: `scripts/agent-validate.sh`, `scripts/lib/test_validate_plan.py` (27/27), `tests/migrations/0.3.0/run.sh`, `tests/migrations/0.4.0/run.sh`.
> - **Eval runner SKIP/FAIL classifier verified** with mock CLI (quota error → exit 77 / SKIP; non-matching output → exit 1 / FAIL). See `tests/evals/test-helpers.sh::is_claude_unavailable_output`.
> - **Behavior evals (4 LLM-driven) currently FAIL when Claude CLI is available** with full quota: `verify-before-claim`, `root-cause-first`, `no-invented-gates`, `plan-grounding`. They are flaky LLM gates and are explicitly **advisory, not a release gate**. Run with `scripts/agent-evals.sh --behavior` only when intentionally dogfooding prompt changes.
> - **Default `--fast` set is deterministic and token-free** (`plugin-command-load` only) — `scripts/agent-evals.sh` exits `0` cleanly on every commit / CI without Claude credentials. This satisfies the "explicitly demote behavior evals out of the release-gate set" condition for promoting to `v0.4.0`.

## 0.3.2 - 2026-04-26

- Aligned `scripts/bootstrap-request.sh` template version with the published Claude plugin metadata. Repos newly bootstrapped at `0.3.2` get a manifest that matches the released plugin tag and remain compatible with the existing `0.3.0` migration; no migration is required to adopt this release.
- Bumped Claude plugin and local marketplace metadata to `0.3.2`.

## 0.3.1 - 2026-04-24

- Added versioned sync tooling for downstream repos with dry-run by default, conflict-stop behavior, explicit `--accept-theirs` overrides, and append-only sync logs.
- Added the `0.2.0` to `0.3.0` migration manifest and mechanical fixture regression test.
- Documented release tag discipline, immutable release tag mapping, and downstream sync usage.
- Bumped Claude plugin and local marketplace metadata to `0.3.1`.

## 0.3.0 - 2026-04-23

- Added `refactor` and `security-review` command prompts backed by existing workflows.
- Updated command validation to require the new command prompts when commands are enabled.
- Added bootstrap target guards so the deterministic script refuses to bootstrap the template source repo into itself.
- Tightened verify gate argument handling to reject unsupported extra arguments.
- Added Codex command-wrapper skills for `--harness codex --features full` instead of using deprecated repo-local `.codex/prompts`.
- Documented Claude permission hardening semantics and added narrow read-only `allowed-tools` hints to review commands.

## 0.2.0 - 2026-04-22

- Added canonical command prompts under `core/commands/` for bootstrap, plan, bugfix, implement, review, verify, and release-check.
- Moved Claude Code plugin commands to the canonical `core/commands/` path to avoid root `commands/` drift.
- Added `.agent/commands/` generation for `standard` and `full` bootstrap feature levels.
- Added `core/command-conventions.md` documenting Claude native slash commands and prompt-based `agent:<name>` convention for non-Claude harnesses.
- Added `release-check-workflow.md` for report-only release readiness checks without deploys, tags, pushes, or remote migrations.
- Added `features_enabled`, gate mode metadata, and `security` gate support to generated manifests and gate templates.
- Updated generated adapters for Codex/generic, Cursor, Copilot, and Gemini to document `agent:<name>` command convention; Claude stays native slash only.
- Updated validation to check command files when the commands feature is enabled while remaining compatible with older generated repos without `.agent/commands/`.
- Bumped the Claude plugin and local marketplace metadata to `0.2.0`.
- Added behavior-shaping guardrails to rulebase and gates templates: verification discipline, root-cause-first language, no invented artifacts, and no unrelated changes.
- Updated generated adapters to require re-reading `.agent/rulebase.md` at the start of coding tasks.
- Added optional SessionStart hook template for supported harnesses.
- Added `.agent/runs/<date>-<slug>/spec.md` and `plan.md` convention for non-trivial work.
- Added subagent prompt fragments under `.agent/roles/prompts/` and corresponding template sources under `core/roles/prompts/`.
- Added optional native skill source files under `core/skills/` for supported harnesses.
- Added GitHub-only pull request template source under `core/github/`; other host merge request templates remain a future extension.
- Added optional worktree workflow source under `core/workflows/worktree-workflow.md`.
- Added behavior eval runner and shared eval helpers; evals require the Claude CLI and skip safely when it is missing.
- Added fast behavior evals for verification-before-claim, root-cause-first, and no-invented-gates behavior.
- Added integration behavior eval for scoped changes and no unrelated cleanup.
- Added integration behavior eval for completing script-first bootstrap pending tasks.
- Added deterministic bootstrap skeleton generator with `.agent/bootstrap-pending.md` handoff.
- Added canonical bootstrap steps document to keep script, prompt, and future skills/plugins aligned.
- Added `bootstrap-agent-system` native skill for completing script-first bootstrap safely.
- Added optional Claude Code plugin layer with `.claude-plugin/plugin.json`, local marketplace metadata, `/agent-bootstrap:bootstrap`, and `bin/agent-bootstrap`.
- Extended validation to require role prompt fragments and behavior-shaping guardrails in generated repos.
- Fixed validator root resolution for nested sample repos and explicit `AGENT_ROOT` overrides.

## 1.0.0 - Initial Template

- Added tool-agnostic `.agent/` core templates.
- Added thin adapters for Codex/OpenAI-style agents, Claude, Gemini, Cursor, and Copilot.
- Added role templates for planner, implementer, reviewer, and gate runner.
- Added workflows for bootstrap, feature, bugfix, refactor, review, security review, improvement cycle, and rule evolution.
- Added LLM instantiation prompt and bootstrap checklist.
- Added deterministic validation script for generated repos.
- Added Node.js sample as a few-shot instantiation reference.
- Added source mapping instructions so LLMs copy canonical template files instead of recreating them.
- Simplified manifest audit fields to `instantiated_at` and `llm_tool_used`.
- Added `USAGE.md` with detailed setup, validation, review, and upgrade guidance.
- Added README and usage references to arXiv:2604.15082 with a short description of how the paper maps to this template.
