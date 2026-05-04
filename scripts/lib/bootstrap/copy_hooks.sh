# Bootstrap: optional hooks under .agent/hooks/.

copy_hook() {
  case "$install_hook_mode" in
    none)
      return 0
      ;;
  esac

  case "$install_hook_mode" in
    session-start|both|all)
      copy_file "$TEMPLATE_ROOT/core/hooks/session-start.sh" "$TARGET_ROOT/.agent/hooks/session-start.sh" "755"
      ;;
  esac

  case "$install_hook_mode" in
    secret-guard|both|all)
      copy_file "$TEMPLATE_ROOT/core/hooks/pre-tool-use-secret-guard.py.template" "$TARGET_ROOT/.agent/hooks/pre-tool-use-secret-guard.py" "755"
      log ""
      log "WARNING: secret-guard hook staged at .agent/hooks/pre-tool-use-secret-guard.py."
      log "         It is OFF until you register it in your harness. Review the script and"
      log "         current PreToolUse schema before enabling. See core/hooks/README.md."
      log ""
      ;;
  esac

  case "$install_hook_mode" in
    rulebase-guard|all)
      copy_file "$TEMPLATE_ROOT/core/hooks/pre-tool-use-rulebase-guard.py.template" "$TARGET_ROOT/.agent/hooks/pre-tool-use-rulebase-guard.py" "755"
      log ""
      log "WARNING: rulebase-guard hook staged at .agent/hooks/pre-tool-use-rulebase-guard.py."
      log "         It is OFF until you register it in your harness. Review the script and"
      log "         current PreToolUse schema before enabling. See core/hooks/README.md."
      log ""
      ;;
  esac
}
