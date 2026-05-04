# Bootstrap: CLI parsing (sourced by scripts/bootstrap-request.sh).
# Bash 3.2 compatible — no associative arrays, namerefs, or Bash 4-only syntax.

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
  --install-hook[=mode]   Stage optional hook(s) under .agent/hooks/.
                          Bare flag is an alias for =session-start.
                          Modes: session-start | secret-guard |
                                 rulebase-guard | both | all
                          - both = session-start + secret-guard (legacy)
                          - all  = session-start + secret-guard + rulebase-guard
                          See core/hooks/README.md before enabling.
  --discover-gates        Discover candidate gate commands from the target repo
                          and insert them as commented stubs in
                          scripts/agent-eval.sh. Adds gate-candidate-discovery
                          to .agent/manifest.json::features_enabled only when
                          at least one stub is inserted. Off by default;
                          runtime gate behavior stays not_configured.
  --with-mcp-discovery    Render the advisory MCP layer into the target:
                          .mcp.json.suggested (NOT .mcp.json),
                          .agent/commands/mcp-discover.md, and the
                          mcp-discovery-suggested feature flag in the
                          manifest. Off by default. The default bootstrap
                          generates no MCP files. Requires --features
                          standard or full (minimal lacks the commands
                          surface the MCP layer references).
                          See core/mcp/README.md.
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
      install_hook_mode="session-start"
      shift
      ;;
    --install-hook=session-start)
      install_hook_mode="session-start"
      shift
      ;;
    --install-hook=secret-guard)
      install_hook_mode="secret-guard"
      shift
      ;;
    --install-hook=both)
      install_hook_mode="both"
      shift
      ;;
    --install-hook=rulebase-guard)
      install_hook_mode="rulebase-guard"
      shift
      ;;
    --install-hook=all)
      install_hook_mode="all"
      shift
      ;;
    --install-hook=*)
      die "unknown --install-hook value: ${1#--install-hook=} (expected session-start, secret-guard, rulebase-guard, both, or all)"
      ;;
    --discover-gates)
      discover_gates="1"
      shift
      ;;
    --with-mcp-discovery)
      with_mcp_discovery="1"
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
