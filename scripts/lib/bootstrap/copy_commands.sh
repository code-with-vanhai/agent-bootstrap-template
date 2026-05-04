# Bootstrap: command prompts under .agent/commands/.

copy_commands() {
  [ "$features" != "minimal" ] || return 0

  _cmd_files="$(find "$TEMPLATE_ROOT/core/commands" -maxdepth 1 -type f -name '*.md' -print | LC_ALL=C sort)"
  [ -n "$_cmd_files" ] || die "missing command files in $TEMPLATE_ROOT/core/commands"

  while IFS= read -r command_file; do
    [ -n "$command_file" ] || continue
    command_name="$(basename "$command_file")"
    render_template "$command_file" "$TARGET_ROOT/.agent/commands/$command_name"
  done <<EOF
$_cmd_files
EOF
}
