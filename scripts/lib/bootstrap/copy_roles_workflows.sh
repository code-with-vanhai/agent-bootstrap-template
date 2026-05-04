# Bootstrap: roles and workflows.

copy_roles() {
  for role in planner implementer reviewer gate-runner; do
    render_template "$TEMPLATE_ROOT/core/roles/${role}.md" "$TARGET_ROOT/.agent/roles/${role}.md"
  done

  for prompt in planner-subagent implementer-subagent reviewer-subagent gate-runner-subagent; do
    render_template "$TEMPLATE_ROOT/core/roles/prompts/${prompt}.md" "$TARGET_ROOT/.agent/roles/prompts/${prompt}.md"
  done
}

copy_workflows() {
  for workflow in bootstrap feature bugfix refactor review security-review improvement-cycle rule-evolution release-check; do
    render_template "$TEMPLATE_ROOT/core/workflows/${workflow}-workflow.md" "$TARGET_ROOT/.agent/workflows/${workflow}-workflow.md"
  done

  if [ "$features" = "full" ]; then
    render_template "$TEMPLATE_ROOT/core/workflows/worktree-workflow.md" "$TARGET_ROOT/.agent/workflows/worktree-workflow.md"
  fi
}
