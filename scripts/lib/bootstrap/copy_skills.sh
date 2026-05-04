# Bootstrap: native skills + Codex command wrapper skills.

copy_skills() {
  [ "$features" = "full" ] || return 0

  skill_dest=""
  case "$harness" in
    codex)
      skill_dest="$TARGET_ROOT/.agents/skills/agent-bootstrap"
      ;;
    claude)
      skill_dest="$TARGET_ROOT/.claude/skills/agent-bootstrap"
      ;;
    *)
      return 0
      ;;
  esac

  _skills="$(find "$TEMPLATE_ROOT/core/skills" -mindepth 2 -maxdepth 2 -type f -name SKILL.md -print | LC_ALL=C sort)"
  while IFS= read -r skill_file; do
    [ -n "$skill_file" ] || continue
    skill_name="$(basename "$(dirname "$skill_file")")"
    copy_file "$skill_file" "$skill_dest/$skill_name/SKILL.md"
  done <<EOF
$_skills
EOF
}

copy_codex_command_skills() {
  [ "$features" = "full" ] || return 0
  [ "$harness" = "codex" ] || return 0

  _cmd_files="$(find "$TEMPLATE_ROOT/core/commands" -maxdepth 1 -type f -name '*.md' -print | LC_ALL=C sort)"
  [ -n "$_cmd_files" ] || die "missing command files in $TEMPLATE_ROOT/core/commands"

  while IFS= read -r command_file; do
    [ -n "$command_file" ] || continue
    command_name="$(basename "$command_file" .md)"
    skill_name="agent-$command_name"
    dest="$TARGET_ROOT/.agents/skills/agent-bootstrap/$skill_name/SKILL.md"

    if [ -e "$dest" ] && [ "$force" != "1" ]; then
      log "SKIP existing $dest"
      record_skipped "$dest"
      continue
    fi

    ensure_dir "$(dirname "$dest")"
    if [ "$dry_run" = "1" ]; then
      log "DRY-RUN write $dest"
    else
      cat > "$dest" <<EOF
---
name: $skill_name
description: Use when the user invokes Agent Bootstrap command $skill_name, agent:$command_name, or asks Codex to run the $command_name agent workflow.
---

# Agent Bootstrap $command_name Command

This is a Codex wrapper skill for the canonical command file.

1. Read \`.agent/commands/$command_name.md\`.
2. Treat the user's current request, including any text after \`$skill_name\` or \`agent:$command_name\`, as the command arguments or task context.
3. Follow \`.agent/commands/$command_name.md\` exactly.
4. Keep \`.agent/commands/$command_name.md\` as the source of truth; do not edit this wrapper when changing command behavior.
EOF
    fi
    record_written "$dest"
  done <<EOF
$_cmd_files
EOF
}
