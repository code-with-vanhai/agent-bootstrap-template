#!/usr/bin/env bash
# Orchestrator for Agent Bootstrap Kit skeleton generation.
# Implementation modules live under scripts/lib/bootstrap/ (sourced with `.`).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BOOTSTRAP_LIB="$SCRIPT_DIR/lib/bootstrap"
DEFAULT_TEMPLATE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

target="."
template_root="$DEFAULT_TEMPLATE_ROOT"
features="standard"
harness="generic"
dry_run="0"
force="0"
install_hook_mode="none"
discover_gates="0"
with_mcp_discovery="0"
template_version="0.10.0"

# shellcheck source=lib/bootstrap/parse_args.sh
. "$BOOTSTRAP_LIB/parse_args.sh"

case "$features" in
  minimal|standard|full) ;;
  *) die "--features must be minimal, standard, or full" ;;
esac

case "$harness" in
  generic|codex|claude|cursor|copilot|gemini) ;;
  *) die "--harness must be generic, codex, claude, cursor, copilot, or gemini" ;;
esac

if [ "$with_mcp_discovery" = "1" ] && [ "$features" = "minimal" ]; then
  die "--with-mcp-discovery requires --features standard or full; minimal does not generate the .agent/commands/ surface that the MCP layer points to"
fi

[ -d "$target" ] || die "target does not exist: $target"
[ -d "$template_root/core" ] || die "template root does not contain core/: $template_root"
[ -f "$template_root/core/bootstrap-steps.md" ] || die "missing core/bootstrap-steps.md in template root"

TARGET_ROOT="$(cd "$target" && pwd)"
TEMPLATE_ROOT="$(cd "$template_root" && pwd)"
project_name="$(basename "$TARGET_ROOT")"
generated_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
source_template="$TEMPLATE_ROOT"
repo_url="$(git -C "$TARGET_ROOT" config --get remote.origin.url 2>/dev/null || true)"
[ -n "$repo_url" ] || repo_url="not confirmed"

if [ "$TARGET_ROOT" = "$TEMPLATE_ROOT" ]; then
  die "target must be a repository that will receive Agent Bootstrap Kit, not the agent-bootstrap-template source repo"
fi

target_plugin_json="$TARGET_ROOT/.claude-plugin/plugin.json"
if [ -f "$target_plugin_json" ] && grep -Eq '"name"[[:space:]]*:[[:space:]]*"agent-bootstrap"' "$target_plugin_json"; then
  die "target appears to be the agent-bootstrap-template source repo because .claude-plugin/plugin.json declares name agent-bootstrap"
fi

if [ -d "$TARGET_ROOT/.agent" ] && [ "$force" != "1" ]; then
  die ".agent/ already exists in $TARGET_ROOT. Use --force to overwrite generated files intentionally."
fi

skipped_files=""
written_files=""
render_token_map_file=""

# shellcheck source=lib/bootstrap/render_token_map.sh
. "$BOOTSTRAP_LIB/render_token_map.sh"

trap cleanup_render_token_map EXIT

# shellcheck source=lib/bootstrap/detect_stack.sh
. "$BOOTSTRAP_LIB/detect_stack.sh"

package_manager="$(detect_package_manager)"
primary_language="$(detect_primary_language)"

# shellcheck source=lib/bootstrap/copy_core.sh
. "$BOOTSTRAP_LIB/copy_core.sh"
# shellcheck source=lib/bootstrap/copy_roles_workflows.sh
. "$BOOTSTRAP_LIB/copy_roles_workflows.sh"
# shellcheck source=lib/bootstrap/copy_commands.sh
. "$BOOTSTRAP_LIB/copy_commands.sh"
# shellcheck source=lib/bootstrap/copy_scripts.sh
. "$BOOTSTRAP_LIB/copy_scripts.sh"
# shellcheck source=lib/bootstrap/copy_adapters.sh
. "$BOOTSTRAP_LIB/copy_adapters.sh"
# shellcheck source=lib/bootstrap/copy_github_metadata.sh
. "$BOOTSTRAP_LIB/copy_github_metadata.sh"
# shellcheck source=lib/bootstrap/copy_skills.sh
. "$BOOTSTRAP_LIB/copy_skills.sh"
# shellcheck source=lib/bootstrap/copy_subagents.sh
. "$BOOTSTRAP_LIB/copy_subagents.sh"
# shellcheck source=lib/bootstrap/copy_hooks.sh
. "$BOOTSTRAP_LIB/copy_hooks.sh"
# shellcheck source=lib/bootstrap/copy_mcp.sh
. "$BOOTSTRAP_LIB/copy_mcp.sh"
# shellcheck source=lib/bootstrap/gate_discovery.sh
. "$BOOTSTRAP_LIB/gate_discovery.sh"
# shellcheck source=lib/bootstrap/write_pending.sh
. "$BOOTSTRAP_LIB/write_pending.sh"

log "Agent Bootstrap Kit skeleton"
log "Target: $TARGET_ROOT"
log "Template: $TEMPLATE_ROOT"
log "Features: $features"
log "Harness: $harness"

features_enabled_json="$(build_features_enabled_json)"
features_enabled_json="$(maybe_add_mcp_feature "$features_enabled_json")"
create_render_token_map

copy_core_files
copy_roles
copy_workflows
copy_commands
copy_scripts
copy_adapters
copy_github_metadata
copy_skills
copy_codex_command_skills
copy_claude_subagents
copy_hook
copy_mcp
discover_gates_into_eval
write_pending

if [ "$dry_run" = "1" ]; then
  log ""
  log "Dry run complete. No files were written."
  exit 0
fi

log ""
log "Written files:$written_files"

if [ -n "$skipped_files" ]; then
  log ""
  log "Skipped existing files:$skipped_files"
fi

log ""
log "Next step:"
log "  Open your coding agent in $TARGET_ROOT and say:"
log "  Complete .agent/bootstrap-pending.md"
