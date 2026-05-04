# Bootstrap: Claude native subagent markdown files.

copy_claude_subagents() {
  [ "$features" = "full" ] || return 0
  [ "$harness" = "claude" ] || return 0

  for role in planner implementer reviewer gate-runner; do
    body_src="$TEMPLATE_ROOT/core/roles/prompts/${role}-subagent.md"
    [ -f "$body_src" ] || die "missing role prompt fragment $body_src"

    case "$role" in
      planner)
        agent_description="Plan non-trivial work in this repo. Read .agent/roles/planner.md, .agent/rulebase.md, .agent/ownership.md, .agent/gates.md, and the relevant workflow before producing .agent/runs/<date>-<slug>/spec.md and plan.md. Do not edit product code or run destructive commands."
        agent_tools="Read, Grep, Glob, Bash"
        agent_disallowed="Edit, Write, MultiEdit"
        agent_permission_mode="plan"
        agent_max_turns="30"
        agent_skills="plan-before-code, no-invented-artifacts"
        ;;
      implementer)
        agent_description="Implement scoped changes for the current run spec. Read .agent/roles/implementer.md, the run plan, and .agent/rulebase.md before editing. Stay within the assigned ownership boundary, run scripts/agent-eval.sh, and stop on uncertainty."
        agent_tools="Read, Edit, Write, MultiEdit, Grep, Glob, Bash"
        agent_disallowed=""
        agent_permission_mode="default"
        agent_max_turns="60"
        agent_skills="scoped-implementation, no-invented-artifacts, no-secret-leakage, data-safety"
        ;;
      reviewer)
        agent_description="Review diffs, plans, or specs against .agent/rulebase.md, the run plan, and the cited evidence. Do not approve unverified completion claims and do not rewrite the implementation unless explicitly asked."
        agent_tools="Read, Grep, Glob, Bash"
        agent_disallowed="Edit, Write, MultiEdit"
        agent_permission_mode="default"
        agent_max_turns="40"
        agent_skills="verify-before-completion, no-invented-artifacts"
        ;;
      gate-runner)
        agent_description="Run the smallest sufficient gate from .agent/gates.md through scripts/agent-eval.sh and report the exact command and result. Do not modify product code to make the gate pass."
        agent_tools="Read, Bash"
        agent_disallowed="Edit, Write, MultiEdit"
        agent_permission_mode="default"
        agent_max_turns="20"
        agent_skills="verify-before-completion"
        ;;
    esac

    dest="$TARGET_ROOT/.claude/agents/${role}.md"
    if [ -e "$dest" ] && [ "$force" != "1" ]; then
      log "SKIP existing $dest"
      record_skipped "$dest"
      continue
    fi

    ensure_dir "$(dirname "$dest")"
    if [ "$dry_run" = "1" ]; then
      log "DRY-RUN write $dest"
      record_written "$dest"
      continue
    fi

    {
      printf -- '---\n'
      printf 'name: %s\n' "$role"
      printf 'description: %s\n' "$agent_description"
      printf 'tools: %s\n' "$agent_tools"
      if [ -n "$agent_disallowed" ]; then
        printf 'disallowedTools: %s\n' "$agent_disallowed"
      fi
      printf 'permissionMode: %s\n' "$agent_permission_mode"
      printf 'maxTurns: %s\n' "$agent_max_turns"
      printf 'skills: %s\n' "$agent_skills"
      printf -- '---\n\n'
      cat "$body_src"
    } > "$dest"

    record_written "$dest"
  done
}
