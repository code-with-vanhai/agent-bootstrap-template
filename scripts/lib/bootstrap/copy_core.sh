# Bootstrap: copy core .agent templates.

copy_core_files() {
  render_template "$TEMPLATE_ROOT/core/README.md" "$TARGET_ROOT/.agent/README.md"
  render_template "$TEMPLATE_ROOT/core/manifest.template.json" "$TARGET_ROOT/.agent/manifest.json"
  render_template "$TEMPLATE_ROOT/core/project-profile.template.md" "$TARGET_ROOT/.agent/project-profile.md"
  render_template "$TEMPLATE_ROOT/core/constitution.template.md" "$TARGET_ROOT/.agent/constitution.md"
  render_template "$TEMPLATE_ROOT/core/rulebase.template.md" "$TARGET_ROOT/.agent/rulebase.md"
  render_template "$TEMPLATE_ROOT/core/ownership.template.md" "$TARGET_ROOT/.agent/ownership.md"
  render_template "$TEMPLATE_ROOT/core/gates.template.md" "$TARGET_ROOT/.agent/gates.md"
  render_template "$TEMPLATE_ROOT/core/decisions.template.md" "$TARGET_ROOT/.agent/decisions.md"
  render_template "$TEMPLATE_ROOT/core/lessons.template.md" "$TARGET_ROOT/.agent/lessons.md"
}
