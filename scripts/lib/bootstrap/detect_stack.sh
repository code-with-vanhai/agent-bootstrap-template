# Bootstrap: target repo stack detection (sourced after TARGET_ROOT is set).

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
      if [ "$harness" = "claude" ]; then
        if is_github_hosted; then
          printf '["baseline", "commands", "github-pr-template", "native-skills", "worktree-workflow", "claude-native-subagents"]'
        else
          printf '["baseline", "commands", "native-skills", "worktree-workflow", "claude-native-subagents"]'
        fi
      elif [ "$harness" = "codex" ]; then
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
