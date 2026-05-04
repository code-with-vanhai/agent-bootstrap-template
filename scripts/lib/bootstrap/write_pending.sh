# Bootstrap: write .agent/bootstrap-pending.md checklist.

write_pending() {
  pending="$TARGET_ROOT/.agent/bootstrap-pending.md"

  if [ -e "$pending" ] && [ "$force" != "1" ]; then
    log "SKIP existing $pending"
    record_skipped "$pending"
    return
  fi

  ensure_dir "$(dirname "$pending")"
  if [ "$dry_run" = "1" ]; then
    log "DRY-RUN write $pending"
    return
  fi

  github_status="not confirmed"
  if is_github_hosted; then
    github_status="confirmed"
  fi

  skills_status="not generated"
  if [ "$features" = "full" ] && { [ "$harness" = "codex" ] || [ "$harness" = "claude" ]; }; then
    skills_status="generated"
  elif [ "$features" = "full" ]; then
    skills_status="not generated: no supported native skill path for harness"
  fi

  command_skill_status="not generated"
  if [ "$features" = "full" ] && [ "$harness" = "codex" ]; then
    command_skill_status="generated"
  fi

  worktree_status="not generated"
  if [ "$features" = "full" ]; then
    worktree_status="generated"
  fi

  commands_status="not generated"
  if [ "$features" != "minimal" ]; then
    commands_status="generated"
  fi

  session_start_hook_status="not generated"
  case "$install_hook_mode" in
    session-start|both|all)
      session_start_hook_status="staged under .agent/hooks/session-start.sh; install manually in the harness"
      ;;
  esac

  secret_guard_hook_status="not generated"
  case "$install_hook_mode" in
    secret-guard|both|all)
      secret_guard_hook_status="staged under .agent/hooks/pre-tool-use-secret-guard.py; install manually in the harness"
      ;;
  esac

  rulebase_guard_hook_status="not generated"
  case "$install_hook_mode" in
    rulebase-guard|all)
      rulebase_guard_hook_status="staged under .agent/hooks/pre-tool-use-rulebase-guard.py; install manually in the harness"
      ;;
  esac

  native_subagents_status="not generated"
  if [ "$features" = "full" ] && [ "$harness" = "claude" ]; then
    native_subagents_status="generated under .claude/agents/"
  elif [ "$features" = "full" ]; then
    native_subagents_status="not generated: no native subagent path for harness"
  fi

  gate_discovery_status="not run"
  if [ "$discover_gates" = "1" ]; then
    if agent_eval_has_candidate_stubs; then
      gate_discovery_status="ran; review commented stubs in scripts/agent-eval.sh and promote only confirmed commands"
    else
      gate_discovery_status="ran; no candidates discovered; marker blocks remain empty"
    fi
  fi

  mcp_discovery_status="not generated"
  if [ "$with_mcp_discovery" = "1" ]; then
    # The orchestrator rejects --features minimal + --with-mcp-discovery
    # before any side effects, so by the time write_pending runs the layer
    # is always genuinely rendered.
    mcp_discovery_status="generated: review .mcp.json.suggested with scripts/lib/validate_mcp_config.py before promoting to .mcp.json"
  fi

  {
    cat <<'EOF'
# Bootstrap Pending Tasks

EOF
    printf 'Generated: %s\n' "$generated_at"
    printf 'Target: %s\n' "$TARGET_ROOT"
    printf 'Template: %s\n' "$TEMPLATE_ROOT"
    printf 'Features: %s\n' "$features"
    printf 'Harness: %s\n' "$harness"
    printf 'GitHub hosting: %s\n' "$github_status"
    printf 'Package manager hint: %s\n' "$package_manager"
    printf 'Primary language hint: %s\n' "$primary_language"
    printf 'Repo remote: %s\n' "$repo_url"
    printf 'Commands: %s\n' "$commands_status"
    printf 'Skills: %s\n' "$skills_status"
    printf 'Codex command wrapper skills: %s\n' "$command_skill_status"
    printf 'Worktree workflow: %s\n' "$worktree_status"
    printf 'SessionStart hook: %s\n' "$session_start_hook_status"
    printf 'PreToolUse secret-guard hook: %s\n' "$secret_guard_hook_status"
    printf 'PreToolUse rulebase-guard hook: %s\n' "$rulebase_guard_hook_status"
    printf 'Claude native subagents: %s\n' "$native_subagents_status"
    printf 'Gate candidate discovery: %s\n' "$gate_discovery_status"
    printf 'MCP discovery layer: %s\n' "$mcp_discovery_status"
    cat <<'EOF'

## What the script already did

- Created the deterministic Agent Bootstrap Kit skeleton.
- Copied canonical `.agent/` files, roles, prompt fragments, workflows, command prompts, adapters, and scripts.
- Replaced template placeholders with conservative values.
- Marked unknown gates and repo facts as `not configured` or `not confirmed`.

## Tasks for the coding agent

- [ ] Scan checked-in repo files before editing generated agent files.
- [ ] Fill `.agent/project-profile.md` with the real stack, framework, runtime, public surface, data surface, dangerous operations, and repository map.
- [ ] Fill `.agent/gates.md` only with commands found in checked-in package/build/task/CI files.
- [ ] Run `bash scripts/agent-gate-discover.sh --write-suggestions` if useful, then promote only reviewed candidates into `.agent/gates.md` and `scripts/agent-eval.sh`.
- [ ] Update `scripts/agent-eval.sh` to run only those verified gate commands.
- [ ] Fill `.agent/ownership.md` with real path ownership and high-risk boundaries.
- [ ] Fill `.agent/manifest.json` with confirmed project metadata.
- [ ] Review `.agent/commands/` if generated and keep commands as thin pointers to workflows.
- [ ] Review generated adapters and preserve any important existing instructions listed below.
- [ ] Run `bash scripts/agent-validate.sh`.
- [ ] Run `bash -n scripts/agent-eval.sh`.
- [ ] Delete `.agent/bootstrap-pending.md` only after the generated agent system is complete.

## Existing files skipped by the script
EOF
    printf '%s\n' "$skipped_files"
    cat <<'EOF'

If this section is empty, no existing generated target files were skipped.

## Hard rules

- Do not modify business logic while completing bootstrap.
- Do not deploy.
- Do not run remote migrations.
- Do not edit secrets or env values.
- Do not invent commands, gates, files, frameworks, ownership, deployment targets, or repo facts.
- If a fact is uncertain, keep it as `not confirmed`.
- If a gate command is missing, keep it as `not configured`.
EOF
  } > "$pending"

  record_written "$pending"
}
