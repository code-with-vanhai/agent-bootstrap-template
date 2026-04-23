#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_TEMPLATE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

target="."
template_root="$DEFAULT_TEMPLATE_ROOT"
features="standard"
harness="generic"
dry_run="0"
force="0"
install_hook="0"
template_version="0.3.0"

usage() {
  cat <<'EOF'
Usage: scripts/bootstrap-request.sh [options]

Creates a deterministic Agent Bootstrap Kit skeleton in a target repository,
then writes .agent/bootstrap-pending.md for the coding agent to complete.

Options:
  --target <path>          Target repository path (default: .)
  --template <path>        agent-bootstrap-template path (default: script parent)
  --features <level>      minimal, standard, or full (default: standard)
  --harness <name>        generic, codex, claude, cursor, copilot, or gemini (default: generic)
  --install-hook          Stage optional SessionStart hook under .agent/hooks/
  --force                 Overwrite existing generated files
  --dry-run               Print actions without writing files
  -h, --help              Show this help

After running, ask your coding agent:

  Complete .agent/bootstrap-pending.md
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

log() {
  printf '%s\n' "$*"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --target)
      [ "$#" -ge 2 ] || die "missing value for --target"
      target="$2"
      shift 2
      ;;
    --template)
      [ "$#" -ge 2 ] || die "missing value for --template"
      template_root="$2"
      shift 2
      ;;
    --features)
      [ "$#" -ge 2 ] || die "missing value for --features"
      features="$2"
      shift 2
      ;;
    --harness)
      [ "$#" -ge 2 ] || die "missing value for --harness"
      harness="$2"
      shift 2
      ;;
    --install-hook)
      install_hook="1"
      shift
      ;;
    --force)
      force="1"
      shift
      ;;
    --dry-run)
      dry_run="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

case "$features" in
  minimal|standard|full) ;;
  *) die "--features must be minimal, standard, or full" ;;
esac

case "$harness" in
  generic|codex|claude|cursor|copilot|gemini) ;;
  *) die "--harness must be generic, codex, claude, cursor, copilot, or gemini" ;;
esac

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

record_written() {
  written_files="${written_files}
- $1"
}

record_skipped() {
  skipped_files="${skipped_files}
- $1"
}

ensure_dir() {
  dir="$1"
  if [ "$dry_run" = "1" ]; then
    log "DRY-RUN mkdir -p $dir"
  else
    mkdir -p "$dir"
  fi
}

copy_file() {
  src="$1"
  dest="$2"
  mode="${3:-}"

  [ -f "$src" ] || die "source file missing: $src"

  if [ -e "$dest" ] && [ "$force" != "1" ]; then
    log "SKIP existing $dest"
    record_skipped "$dest"
    return
  fi

  ensure_dir "$(dirname "$dest")"
  if [ "$dry_run" = "1" ]; then
    log "DRY-RUN copy $src -> $dest"
  else
    cp "$src" "$dest"
    if [ -n "$mode" ]; then
      chmod "$mode" "$dest"
    fi
  fi
  record_written "$dest"
}

escape_sed_replacement() {
  printf '%s' "$1" | sed -e 's/[\/&]/\\&/g'
}

replace_token() {
  file="$1"
  token="$2"
  value="$(escape_sed_replacement "$3")"
  sed -i "s/{{${token}}}/${value}/g" "$file"
}

detect_package_manager() {
  if [ -f "$TARGET_ROOT/pnpm-lock.yaml" ] || [ -f "$TARGET_ROOT/pnpm-workspace.yaml" ]; then
    printf 'pnpm'
  elif [ -f "$TARGET_ROOT/yarn.lock" ]; then
    printf 'yarn'
  elif [ -f "$TARGET_ROOT/package-lock.json" ]; then
    printf 'npm'
  elif [ -f "$TARGET_ROOT/package.json" ]; then
    printf 'npm'
  elif [ -f "$TARGET_ROOT/Cargo.toml" ]; then
    printf 'cargo'
  elif [ -f "$TARGET_ROOT/go.mod" ]; then
    printf 'go'
  elif [ -f "$TARGET_ROOT/pyproject.toml" ]; then
    printf 'python'
  elif [ -f "$TARGET_ROOT/pom.xml" ]; then
    printf 'maven'
  elif [ -f "$TARGET_ROOT/build.gradle" ] || [ -f "$TARGET_ROOT/build.gradle.kts" ]; then
    printf 'gradle'
  else
    printf 'not confirmed'
  fi
}

detect_primary_language() {
  if [ -f "$TARGET_ROOT/package.json" ]; then
    printf 'JavaScript/TypeScript'
  elif [ -f "$TARGET_ROOT/Cargo.toml" ]; then
    printf 'Rust'
  elif [ -f "$TARGET_ROOT/go.mod" ]; then
    printf 'Go'
  elif [ -f "$TARGET_ROOT/pyproject.toml" ] || [ -f "$TARGET_ROOT/requirements.txt" ]; then
    printf 'Python'
  elif [ -f "$TARGET_ROOT/pom.xml" ] || [ -f "$TARGET_ROOT/build.gradle" ] || [ -f "$TARGET_ROOT/build.gradle.kts" ]; then
    printf 'Java/Kotlin'
  else
    printf 'not confirmed'
  fi
}

package_manager="$(detect_package_manager)"
primary_language="$(detect_primary_language)"
features_enabled_json="[]"

render_template() {
  src="$1"
  dest="$2"

  copy_file "$src" "$dest"
  [ "$dry_run" = "1" ] && return
  [ -f "$dest" ] || return

  replace_token "$dest" "INSTANTIATED_AT_ISO8601" "$generated_at"
  replace_token "$dest" "TEMPLATE_VERSION" "$template_version"
  replace_token "$dest" "FEATURES_ENABLED_JSON_ARRAY" "$features_enabled_json"
  replace_token "$dest" "LLM_TOOL_USED" "bootstrap-request.sh skeleton; agent completion pending"
  replace_token "$dest" "REPO_NAME" "$project_name"
  replace_token "$dest" "AGENT_BOOTSTRAP_TEMPLATE_REPO_URL_OR_PATH" "$source_template"
  replace_token "$dest" "PROJECT_NAME" "$project_name"
  replace_token "$dest" "PRIMARY_LANGUAGE" "$primary_language"
  replace_token "$dest" "PACKAGE_MANAGER_OR_NOT_APPLICABLE" "$package_manager"
  replace_token "$dest" "FRAMEWORK_1" "not confirmed"
  replace_token "$dest" "DEPLOYMENT_TARGET_1" "not configured"
  replace_token "$dest" "CONFIGURED_OR_NOT_CONFIGURED" "not configured"
  replace_token "$dest" "CHANGED_GATE_COMMANDS" "not configured"
  replace_token "$dest" "FAST_GATE_COMMANDS" "not configured"
  replace_token "$dest" "FRONTEND_GATE_COMMANDS" "not configured"
  replace_token "$dest" "BACKEND_GATE_COMMANDS" "not configured"
  replace_token "$dest" "SHARED_GATE_COMMANDS" "not configured"
  replace_token "$dest" "E2E_GATE_COMMANDS" "not configured"
  replace_token "$dest" "FULL_GATE_COMMANDS" "not configured"
  replace_token "$dest" "SECURITY_GATE_COMMANDS" "not configured"
  replace_token "$dest" "RELEASE_GATE_COMMANDS" "not configured"
  replace_token "$dest" "NOT_CONFIGURED_GATE_OR_EMPTY_ARRAY" "not configured"
  replace_token "$dest" "ONE_PARAGRAPH_DESCRIPTION_OF_THE_PRODUCT_OR_LIBRARY" "Bootstrap skeleton generated by script. Complete repo-specific description from checked-in evidence before deleting .agent/bootstrap-pending.md."

  sed -i -E 's/\{\{[A-Z0-9_]+\}\}/not confirmed - complete .agent\/bootstrap-pending.md/g' "$dest"
}

is_github_hosted() {
  if [ -d "$TARGET_ROOT/.github" ]; then
    return 0
  fi
  if printf '%s\n' "$repo_url" | grep -qi 'github.com'; then
    return 0
  fi
  return 1
}

build_features_enabled_json() {
  case "$features" in
    minimal)
      printf '["baseline"]'
      ;;
    standard)
      if is_github_hosted; then
        printf '["baseline", "commands", "github-pr-template"]'
      else
        printf '["baseline", "commands"]'
      fi
      ;;
    full)
      if [ "$harness" = "codex" ] || [ "$harness" = "claude" ]; then
        if is_github_hosted; then
          printf '["baseline", "commands", "github-pr-template", "native-skills", "worktree-workflow"]'
        else
          printf '["baseline", "commands", "native-skills", "worktree-workflow"]'
        fi
      elif is_github_hosted; then
        printf '["baseline", "commands", "github-pr-template", "worktree-workflow"]'
      else
        printf '["baseline", "commands", "worktree-workflow"]'
      fi
      ;;
  esac
}

copy_core_files() {
  render_template "$TEMPLATE_ROOT/core/README.md" "$TARGET_ROOT/.agent/README.md"
  render_template "$TEMPLATE_ROOT/core/manifest.template.json" "$TARGET_ROOT/.agent/manifest.json"
  render_template "$TEMPLATE_ROOT/core/project-profile.template.md" "$TARGET_ROOT/.agent/project-profile.md"
  render_template "$TEMPLATE_ROOT/core/rulebase.template.md" "$TARGET_ROOT/.agent/rulebase.md"
  render_template "$TEMPLATE_ROOT/core/ownership.template.md" "$TARGET_ROOT/.agent/ownership.md"
  render_template "$TEMPLATE_ROOT/core/gates.template.md" "$TARGET_ROOT/.agent/gates.md"
  render_template "$TEMPLATE_ROOT/core/decisions.template.md" "$TARGET_ROOT/.agent/decisions.md"
  render_template "$TEMPLATE_ROOT/core/lessons.template.md" "$TARGET_ROOT/.agent/lessons.md"
}

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

copy_commands() {
  [ "$features" != "minimal" ] || return 0

  set -- "$TEMPLATE_ROOT"/core/commands/*.md
  [ -e "$1" ] || die "missing command files in $TEMPLATE_ROOT/core/commands"

  for command_file in "$@"; do
    command_name="$(basename "$command_file")"
    render_template "$command_file" "$TARGET_ROOT/.agent/commands/$command_name"
  done
}

copy_scripts() {
  copy_file "$TEMPLATE_ROOT/scripts/agent-validate.sh" "$TARGET_ROOT/scripts/agent-validate.sh" "755"
  copy_file "$TEMPLATE_ROOT/scripts/agent-eval.template.sh" "$TARGET_ROOT/scripts/agent-eval.sh" "755"
}

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

copy_github_metadata() {
  if [ "$features" = "minimal" ]; then
    return 0
  fi

  if is_github_hosted; then
    copy_file "$TEMPLATE_ROOT/core/github/PULL_REQUEST_TEMPLATE.md" "$TARGET_ROOT/.github/PULL_REQUEST_TEMPLATE.md"
  fi
  return 0
}

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

  for skill_file in "$TEMPLATE_ROOT"/core/skills/*/SKILL.md; do
    skill_name="$(basename "$(dirname "$skill_file")")"
    copy_file "$skill_file" "$skill_dest/$skill_name/SKILL.md"
  done
}

copy_codex_command_skills() {
  [ "$features" = "full" ] || return 0
  [ "$harness" = "codex" ] || return 0

  set -- "$TEMPLATE_ROOT"/core/commands/*.md
  [ -e "$1" ] || die "missing command files in $TEMPLATE_ROOT/core/commands"

  for command_file in "$@"; do
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
  done
}

copy_hook() {
  [ "$install_hook" = "1" ] || return 0
  copy_file "$TEMPLATE_ROOT/core/hooks/session-start.sh" "$TARGET_ROOT/.agent/hooks/session-start.sh" "755"
}

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

  hook_status="not generated"
  if [ "$install_hook" = "1" ]; then
    hook_status="staged under .agent/hooks/session-start.sh; install manually in the harness"
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
    printf 'SessionStart hook: %s\n' "$hook_status"
    cat <<'EOF'

## What the script already did

- Created the deterministic Agent Bootstrap Kit skeleton.
- Copied canonical `.agent/` files, roles, prompt fragments, workflows, command prompts, adapters, and scripts.
- Replaced template placeholders with conservative values.
- Marked unknown gates and repo facts as `not configured` or `not confirmed`.

## Tasks for the coding agent

- [ ] Scan checked-in repo files before editing generated agent files.
- [ ] Fill `.agent/project-profile.md` with the real stack, framework, runtime, public surface, dangerous operations, and repository map.
- [ ] Fill `.agent/gates.md` only with commands found in checked-in package/build/task/CI files.
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

log "Agent Bootstrap Kit skeleton"
log "Target: $TARGET_ROOT"
log "Template: $TEMPLATE_ROOT"
log "Features: $features"
log "Harness: $harness"

features_enabled_json="$(build_features_enabled_json)"

copy_core_files
copy_roles
copy_workflows
copy_commands
copy_scripts
copy_adapters
copy_github_metadata
copy_skills
copy_codex_command_skills
copy_hook
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
