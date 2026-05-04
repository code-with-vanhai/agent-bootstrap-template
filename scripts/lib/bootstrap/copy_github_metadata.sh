# Bootstrap: GitHub-specific metadata when the target looks GitHub-hosted.

copy_github_metadata() {
  if [ "$features" = "minimal" ]; then
    return 0
  fi

  if is_github_hosted; then
    copy_file "$TEMPLATE_ROOT/core/github/PULL_REQUEST_TEMPLATE.md" "$TARGET_ROOT/.github/PULL_REQUEST_TEMPLATE.md"
  fi
  return 0
}
