# Bootstrap: scripts and Python libraries copied into the target.

copy_scripts() {
  copy_file "$TEMPLATE_ROOT/scripts/agent-validate.sh" "$TARGET_ROOT/scripts/agent-validate.sh" "755"
  copy_file "$TEMPLATE_ROOT/scripts/agent-audit-log.sh" "$TARGET_ROOT/scripts/agent-audit-log.sh" "755"
  copy_file "$TEMPLATE_ROOT/scripts/agent-eval.template.sh" "$TARGET_ROOT/scripts/agent-eval.sh" "755"
  copy_file "$TEMPLATE_ROOT/scripts/agent-gate-discover.sh" "$TARGET_ROOT/scripts/agent-gate-discover.sh" "755"
  copy_file "$TEMPLATE_ROOT/scripts/agent-validate-plan.sh" "$TARGET_ROOT/scripts/agent-validate-plan.sh" "755"
  copy_file "$TEMPLATE_ROOT/scripts/lib/__init__.py" "$TARGET_ROOT/scripts/lib/__init__.py" "644"
  copy_file "$TEMPLATE_ROOT/scripts/lib/audit_log.py" "$TARGET_ROOT/scripts/lib/audit_log.py" "644"
  copy_file "$TEMPLATE_ROOT/scripts/lib/gate_discovery.py" "$TARGET_ROOT/scripts/lib/gate_discovery.py" "644"
  copy_file "$TEMPLATE_ROOT/scripts/lib/gate_modes.py" "$TARGET_ROOT/scripts/lib/gate_modes.py" "644"
  copy_file "$TEMPLATE_ROOT/scripts/lib/insert_gate_candidates.py" "$TARGET_ROOT/scripts/lib/insert_gate_candidates.py" "644"
  copy_file "$TEMPLATE_ROOT/scripts/lib/validate_agent_system.py" "$TARGET_ROOT/scripts/lib/validate_agent_system.py" "644"
  _asv="$(find "$TEMPLATE_ROOT/scripts/lib/agent_system_validation" -maxdepth 1 -type f -name '*.py' -print | LC_ALL=C sort)"
  while IFS= read -r agent_system_validation_file; do
    [ -n "$agent_system_validation_file" ] || continue
    copy_file "$agent_system_validation_file" "$TARGET_ROOT/scripts/lib/agent_system_validation/$(basename "$agent_system_validation_file")" "644"
  done <<EOF
$_asv
EOF
  copy_file "$TEMPLATE_ROOT/scripts/lib/validate_plan.py" "$TARGET_ROOT/scripts/lib/validate_plan.py" "644"
  copy_file "$TEMPLATE_ROOT/scripts/lib/validate_mcp_config.py" "$TARGET_ROOT/scripts/lib/validate_mcp_config.py" "644"
  _pv="$(find "$TEMPLATE_ROOT/scripts/lib/plan_validation" -maxdepth 1 -type f -name '*.py' -print | LC_ALL=C sort)"
  while IFS= read -r plan_validation_file; do
    [ -n "$plan_validation_file" ] || continue
    copy_file "$plan_validation_file" "$TARGET_ROOT/scripts/lib/plan_validation/$(basename "$plan_validation_file")" "644"
  done <<EOF
$_pv
EOF
}
