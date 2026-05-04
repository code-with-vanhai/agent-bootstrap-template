# Bootstrap: thin adapter files at repo root / harness paths.

copy_adapters() {
  copy_file "$TEMPLATE_ROOT/adapters/AGENTS.md" "$TARGET_ROOT/AGENTS.md"

  case "$harness" in
    claude)
      copy_file "$TEMPLATE_ROOT/adapters/CLAUDE.md" "$TARGET_ROOT/CLAUDE.md"
      ;;
    cursor)
      copy_file "$TEMPLATE_ROOT/adapters/cursor-agent-system.mdc" "$TARGET_ROOT/.cursor/rules/agent-system.mdc"
      ;;
    copilot)
      copy_file "$TEMPLATE_ROOT/adapters/copilot-instructions.md" "$TARGET_ROOT/.github/copilot-instructions.md"
      ;;
    gemini)
      copy_file "$TEMPLATE_ROOT/adapters/GEMINI.md" "$TARGET_ROOT/GEMINI.md"
      ;;
    codex|generic)
      ;;
  esac
}
