# Plan: Claude Native Subagents (P0-2)

**Status:** Verified with evidence: agent-validate.sh @ 2026-04-29T03:59:48Z (exit=0)
**Date:** 2026-04-29
**Ref commit:** `c525be4` (pre-implementation; evidence blocks below are `historical-code` after impl landed)
**Plan location note:** Stored under `docs/plans/bootstrap-090/p0-2-claude-subagents/` because this template repo dogfoods plans there; generated target repos should use `.agent/runs/<date>-<slug>/`.

## Goal

Generate native Claude Code `.claude/agents/<role>.md` files for the four existing role prompt fragments when and only when bootstrap is run with `--harness claude --features full`.

## Run Artifact

`docs/plans/bootstrap-090/p0-2-claude-subagents/{spec.md,plan.md}`

## Affected Areas

- `scripts/bootstrap-request.sh` — feature flag computation, generation function, pending summary, call order.
- `core/instantiation-prompt.md` — manual adaptation guidance becomes script-generated behavior for Claude full bootstrap.
- `scripts/lib/validate_agent_system.py` — generated-mode checks for the new feature marker.
- `scripts/lib/test_validate_agent_system.py` — generated Claude full fixture and negative coverage for other harnesses.
- Potential docs: `README.md`, `USAGE.md`, `core/bootstrap-checklist.md`, and `core/bootstrap-steps.md` if implementation changes user-visible generated outputs.

## Owner

Implementer role. Reviewer should inspect generated-file shape and validation behavior before merge because the change touches bootstrap output contracts.

## Implementation Plan

1. Add a small role metadata table in `scripts/bootstrap-request.sh` for `planner`, `implementer`, `reviewer`, and `gate-runner`, matching the role matrix in `spec.md`.
2. Add `claude-native-subagents` to `build_features_enabled_json()` only for `features=full` and `harness=claude`.
3. Add `copy_claude_subagents()` after `copy_skills()`. It should return unless `features=full` and `harness=claude`, then write `.claude/agents/<role>.md` files by prepending frontmatter to `core/roles/prompts/<role>-subagent.md`.
4. Use `copy_file`/`ensure_dir` patterns already present in `bootstrap-request.sh`, but write generated files directly because the frontmatter is synthesized rather than copied from a single source file.
5. Update `write_pending()` to report Claude native subagents as generated when applicable.
6. Update `core/instantiation-prompt.md` so line-level guidance says the deterministic script generates `.claude/agents/<role>.md` for `--harness claude --features full`; manual adaptation remains only for non-script/manual bootstrap paths.
7. Extend generated-mode validation: if `.agent/manifest.json` has `claude-native-subagents`, require four `.claude/agents/{planner,implementer,reviewer,gate-runner}.md` files and validate frontmatter contains `name`, `description`, and `tools`; also assert no `model:` line is emitted.
8. Add tests for `--harness claude --features full`, `--harness codex --features full`, and standard generated repos.
9. Run verification gates listed below.

## Acceptance Criteria

| ID | Criterion | Verification Method | Gate |
|---|---|---|---|
| AC-1 | `--harness claude --features full` generates exactly four native files under `.claude/agents/` with role filenames `planner.md`, `implementer.md`, `reviewer.md`, `gate-runner.md` | `AUTOMATED-UNIT` | `python3 -m unittest scripts.lib.test_validate_agent_system` |
| AC-2 | Generated Claude full `.agent/manifest.json` includes `claude-native-subagents` in `features_enabled` | `AUTOMATED-UNIT` | same |
| AC-3 | Generated Codex full repos do not include `claude-native-subagents` and do not require `.claude/agents/` | `AUTOMATED-UNIT` | same |
| AC-4 | Each generated native agent file contains frontmatter fields `name`, `description`, `tools`, `permissionMode`, `maxTurns`, and `skills` | `AUTOMATED-UNIT` | same |
| AC-5 | Generated native agent files do not include `model:` | `AUTOMATED-UNIT` | same |
| AC-6 | Planner native agent has `Bash` in tools and `Edit, Write, MultiEdit` in `disallowedTools` | `AUTOMATED-UNIT` | same |
| AC-7 | Implementer native agent has edit/write tools and no emitted `disallowedTools` field | `AUTOMATED-UNIT` | same |
| AC-8 | `scripts/agent-validate.sh` passes in the source repo | `AUTOMATED-INTEGRATION` | `scripts/agent-validate.sh` |
| AC-9 | Deterministic evals remain green | `AUTOMATED-INTEGRATION` | `bash scripts/agent-evals.sh --fast` |
| AC-10 | P0-2 plan artifact validates with strict mode before implementation | `AUTOMATED-INTEGRATION` | `scripts/agent-validate-plan.sh --force --strict docs/plans/bootstrap-090/p0-2-claude-subagents` |

## Existing Behaviors Preserved

- `scripts/bootstrap-request.sh:321-346` — existing feature list behavior is `PRESERVED` for `minimal`, `standard`, non-Claude `full`, and Codex `full`; only Claude `full` adds `claude-native-subagents`. Source:

<!-- historical-code path=scripts/bootstrap-request.sh lines=321-346 ref=c525be4 region_sha256=084f43e632cfe7fb2b37c61910d743cc5f128e5afa4a110350e9189ff78ef751 -->
```bash
build_features_enabled_json() {
  case "$features" in
    minimal)
      printf '["baseline"]'
      ;;
    standard)
      if is_github_hosted; then
        printf '["baseline", "commands", "github-pr-template"]'
      else
        printf '["baseline", "commands"]'
      fi
      ;;
    full)
      if [ "$harness" = "codex" ] || [ "$harness" = "claude" ]; then
        if is_github_hosted; then
          printf '["baseline", "commands", "github-pr-template", "native-skills", "worktree-workflow"]'
        else
          printf '["baseline", "commands", "native-skills", "worktree-workflow"]'
        fi
      elif is_github_hosted; then
        printf '["baseline", "commands", "github-pr-template", "worktree-workflow"]'
      else
        printf '["baseline", "commands", "worktree-workflow"]'
      fi
      ;;
  esac
```
<!-- /historical-code -->

- `scripts/bootstrap-request.sh:360-367` — `.agent/roles/*` and `.agent/roles/prompts/*` generation is `PRESERVED`. Native Claude agents are additional outputs and do not replace canonical prompt fragments. Source:

<!-- historical-code path=scripts/bootstrap-request.sh lines=360-367 ref=c525be4 region_sha256=968eb6adb5c88e331c39d251c8b6a296bd40dfb4842b5896f7f701c7a630e29f -->
```bash
copy_roles() {
  for role in planner implementer reviewer gate-runner; do
    render_template "$TEMPLATE_ROOT/core/roles/${role}.md" "$TARGET_ROOT/.agent/roles/${role}.md"
  done

  for prompt in planner-subagent implementer-subagent reviewer-subagent gate-runner-subagent; do
    render_template "$TEMPLATE_ROOT/core/roles/prompts/${prompt}.md" "$TARGET_ROOT/.agent/roles/prompts/${prompt}.md"
  done
```
<!-- /historical-code -->

- `scripts/bootstrap-request.sh:438-447` — native skill generation is `PRESERVED`. `.claude/skills/agent-bootstrap/*` remains skill output; `.claude/agents/*` is a separate native subagent output. Source:

<!-- historical-code path=scripts/bootstrap-request.sh lines=438-447 ref=c525be4 region_sha256=54b14ab8e272090240bd6816056bc9dbff2490fbd29090e46e9996899e24903a -->
```bash
copy_skills() {
  [ "$features" = "full" ] || return 0

  skill_dest=""
  case "$harness" in
    codex)
      skill_dest="$TARGET_ROOT/.agents/skills/agent-bootstrap"
      ;;
    claude)
      skill_dest="$TARGET_ROOT/.claude/skills/agent-bootstrap"
```
<!-- /historical-code -->

- `scripts/bootstrap-request.sh:628-637` — bootstrap call order is `PRESERVED` except for adding `copy_claude_subagents` after `copy_skills` and before pending write. This keeps core files, prompts, scripts, adapters, metadata, and skills behavior unchanged. Source:

<!-- historical-code path=scripts/bootstrap-request.sh lines=628-637 ref=c525be4 region_sha256=787446d815ebeb3a23e8727dc3fb891c36b287f9f75a440841fd0c45eef08459 -->
```bash
copy_core_files
copy_roles
copy_workflows
copy_commands
copy_scripts
copy_adapters
copy_github_metadata
copy_skills
copy_codex_command_skills
copy_hook
```
<!-- /historical-code -->

- `core/instantiation-prompt.md:166-170` — manual adaptation guidance is `BUG FIX`. It is currently accurate but leaves a manual step for Claude full bootstrap. P0-2 changes this to deterministic script output for the supported case while preserving manual fallback language. Source:

<!-- historical-code path=core/instantiation-prompt.md lines=166-170 ref=c525be4 region_sha256=b95dcecbbdc3c2ca3c1b81b3ce779b4379b5aaca785a1eb31e0b5b2a42a9c093 -->
```md
| `core/hooks/session-start.sh` | harness-specific hook path | Optional only; copy when the user requests SessionStart context injection |
| `core/skills/*/SKILL.md` | `.agents/skills/agent-bootstrap/<skill>/SKILL.md` or `.claude/skills/agent-bootstrap/<skill>/SKILL.md` | Optional only; copy when the harness supports native skills |
| `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `core/commands/*.md`, `bin/agent-bootstrap` | Claude Code plugin install | Optional template-level distribution layer; do not copy plugin metadata into target repos |

If the target harness is Claude Code and the user wants dispatchable agents, adapt `.agent/roles/prompts/*-subagent.md` into `.claude/agents/<role>.md`. Otherwise keep prompt fragments under `.agent/roles/prompts/` for copy/paste or manual delegation.
```
<!-- /historical-code -->

- `scripts/lib/validate_agent_system.py:501-521` — generated-mode command and adapter checks are `PRESERVED`; P0-2 adds a separate conditional block keyed by `claude-native-subagents`. Existing adapters still only need to point to `.agent/`. Source:

<!-- historical-code path=scripts/lib/validate_agent_system.py lines=501-521 ref=c525be4 region_sha256=0e623f56c5f6e54a6089991338529dfd5fd65e18897956d083ab551d4f74b017 -->
```python
        commands_enabled = (self.root / ".agent/commands").is_dir() or self.manifest_has_feature(manifest, "commands")
        if commands_enabled:
            self.exists(".agent/workflows/release-check-workflow.md")
            self.contains(".agent/gates.md", "scripts/agent-eval.sh <mode>", ".agent/gates.md documents gate mode signature")
            self.validate_command_files(".agent/commands")
        else:
            self.skip(".agent/commands not generated for this repo")
            if (self.root / ".agent/workflows/release-check-workflow.md").is_file():
                self.contains(".agent/workflows/release-check-workflow.md", "report-only", ".agent/workflows/release-check-workflow.md is report-only")
            else:
                self.skip(".agent/workflows/release-check-workflow.md not generated for this repo")

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

- `scripts/lib/test_validate_agent_system.py:159-165` — existing Codex full generated validation is `PRESERVED`; P0-2 adds Claude-specific generated tests rather than changing this assertion. Source:

<!-- current-code path=scripts/lib/test_validate_agent_system.py lines=159-165 ref=c525be4 region_sha256=28e30fdbb69677dc4d0d5eae10279b73c6effb98d552ee469f7ece01b09cfaea -->
```python
    def test_generated_full_codex_passes(self):
        target = self.make_target(features="full", harness="codex")
        result = self.run_validator("--mode", "generated", "--format", "json", root=target)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["mode"], "generated")
        self.assertEqual(payload["failure_count"], 0)
```
<!-- /current-code -->

## Verification

Pre-implementation plan validation:

```bash
scripts/agent-validate-plan.sh --force --strict docs/plans/bootstrap-090/p0-2-claude-subagents
```

Post-implementation gates:

```bash
python3 -m unittest scripts.lib.test_validate_agent_system
scripts/agent-validate.sh
bash scripts/agent-evals.sh --fast
scripts/agent-validate-plan.sh --force --strict docs/plans/bootstrap-090/p0-2-claude-subagents
```

## Required Gates

- `scripts/agent-validate-plan.sh --force --strict docs/plans/bootstrap-090/p0-2-claude-subagents` before implementation.
- `python3 -m unittest scripts.lib.test_validate_agent_system` after implementation.
- `scripts/agent-validate.sh` after implementation.
- `bash scripts/agent-evals.sh --fast` after implementation.

## Docs/Tests/Contracts To Update

- Docs: `core/instantiation-prompt.md`; likely `README.md`, `USAGE.md`, `core/bootstrap-checklist.md`, and `core/bootstrap-steps.md` if generated layout docs need the new `.claude/agents` output.
- Tests: `scripts/lib/test_validate_agent_system.py`.
- Contracts: `.agent/manifest.json` `features_enabled` gains `claude-native-subagents` for Claude full bootstrap only.

## Decision Ledger

| Decision | Chosen Behavior | Rationale | Alternatives Rejected | Caller/User Impact | Verification |
|---|---|---|---|---|---|
| Feature flag | Add `claude-native-subagents` only for `--harness claude --features full` | Makes generated-mode validation conditional and avoids false failures for other harnesses | Reuse `native-skills` to imply agents; would conflate skills and agents | Claude full repos get explicit manifest evidence; other repos unchanged | `test_generated_full_claude_subagents_passes` |
| Model pinning | Do not emit `model` | Model availability and budget are repo-specific | Hardcode a current Claude model; creates churn and may fail for users without access | Repo owners can add model policy later | Assert no generated file contains `model:` |
| Planner tools | Include `Bash`, deny `Edit`, `Write`, `MultiEdit`, use `permissionMode: plan` | Planner needs read-only git/hash commands for evidence blocks but must not edit code | Remove Bash; would make evidence generation harder. Allow edit tools; weakens planning boundary | Planning agent can inspect and hash without writing | Planner frontmatter test |
| Implementer denied tools | Omit `disallowedTools` for implementer | Implementer role needs edit/write tools by design | Add empty `disallowedTools`; ambiguous frontmatter noise | Generated file stays concise and intentional | Implementer frontmatter test |
| Max turns | Planner 30, implementer 60, reviewer 40, gate-runner 20 | Bounds runaway delegation while matching role complexity | No limits; easier but weaker governance. Same limit for all roles; ignores role scope | Claude users get conservative defaults they can tune | Frontmatter field tests |
| Generation source | Copy body from `core/roles/prompts/<role>-subagent.md` after synthesized frontmatter | Keeps prompt fragments canonical | Maintain separate agent body templates; adds drift risk | One source of truth for role prompt text | Body contains source heading test |
| Validation scope | Generated-mode validates `.claude/agents` only when manifest has `claude-native-subagents` | Avoids requiring Claude files for Codex/generic targets | Always check `.claude/agents`; breaks non-Claude generated repos | Harness-specific validation stays precise | Codex/generic generated tests |

## Contract Value Table

| Literal | Producer | Consumer | User-facing behavior | Test |
|---|---|---|---|---|
| `claude-native-subagents` | `scripts/bootstrap-request.sh::build_features_enabled_json` | `scripts/lib/validate_agent_system.py::validate_generated` | Generated Claude full repos validate that native agents exist | `test_generated_full_claude_subagents_passes` |
| `.claude/agents/planner.md` | `scripts/bootstrap-request.sh::copy_claude_subagents` | Claude Code native subagent loader; validator generated-mode | Planner can be dispatched natively in Claude Code | generated fixture asserts file and frontmatter |
| `.claude/agents/implementer.md` | same | same | Implementer can be dispatched natively in Claude Code | generated fixture asserts file and frontmatter |
| `.claude/agents/reviewer.md` | same | same | Reviewer can be dispatched natively in Claude Code | generated fixture asserts file and frontmatter |
| `.claude/agents/gate-runner.md` | same | same | Gate runner can be dispatched natively in Claude Code | generated fixture asserts file and frontmatter |

## Test Delta

| Test | Action | Why |
|---|---|---|
| `test_generated_full_claude_subagents_passes` | `ADD` | Bootstraps `--harness claude --features full`; validates manifest feature and four `.claude/agents` files |
| `test_generated_full_codex_passes` | `UPDATE` | Confirms Codex full remains valid and does not require Claude subagents |
| `test_generated_standard_passes_through_wrapper_with_agent_root` | `KEEP` | Confirms standard generated repos remain unaffected |
| `tests/evals/codex-harness-fixture.sh` | `KEEP` | Confirms deterministic Codex full eval remains unaffected |

## Risks

- Risk: Generated frontmatter syntax may drift from Claude Code expectations. Mitigation: use only stable documented fields and keep validation focused on field presence, not exhaustive Claude parser emulation.
- Risk: Adding `claude-native-subagents` to all full harnesses would break non-Claude generated validation. Mitigation: feature flag is only emitted for `harness=claude`.
- Risk: Duplicating role prompt bodies into native agent files could drift from `.agent/roles/prompts`. Mitigation: generation reads the canonical prompt fragments at bootstrap time and does not maintain separate body templates.
- Risk: Planner with `Bash` could run unsafe commands. Mitigation: `permissionMode: plan`, denied write tools, and prompt body hard rules still prohibit destructive actions; Bash is needed for git/hash evidence.
- Risk: Tests only inspect generated files, not actual Claude Code runtime loading. Mitigation: this is appropriate for deterministic template CI; runtime loading remains a harness integration concern.
