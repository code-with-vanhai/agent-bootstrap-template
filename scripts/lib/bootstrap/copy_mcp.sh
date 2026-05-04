# Bootstrap: opt-in MCP layer (off by default).
#
# Triggered by --with-mcp-discovery on scripts/bootstrap-request.sh.
# When OFF (default), this helper is a no-op and the bootstrap output is
# byte-identical to a pre-Stage-5 run.
#
# When ON it generates only advisory artifacts:
#   - .mcp.json.suggested (NOT .mcp.json)
#   - .agent/commands/mcp-discover.md (rendered command file)
#   - For codex full bootstrap, the agent-mcp-discover Codex wrapper skill
# It NEVER writes an active .mcp.json.

maybe_add_mcp_feature() {
  json="$1"
  if [ "$with_mcp_discovery" != "1" ]; then
    printf '%s' "$json"
    return 0
  fi
  FEATURES_JSON_INPUT="$json" python3 - <<'PY'
import json
import os
import sys

data = json.loads(os.environ["FEATURES_JSON_INPUT"])
if not isinstance(data, list):
    raise SystemExit(
        f"features_enabled JSON must be a list, got {type(data).__name__}"
    )
if "mcp-discovery-suggested" not in data:
    data.append("mcp-discovery-suggested")
sys.stdout.write(json.dumps(data))
PY
}

copy_mcp() {
  if [ "$with_mcp_discovery" != "1" ]; then
    return 0
  fi
  # The orchestrator already fails fast when --features minimal is combined
  # with --with-mcp-discovery, so reaching here implies a commands surface.
  if [ "$features" = "minimal" ]; then
    die "internal: copy_mcp reached with features=minimal; orchestrator gate is missing"
  fi

  copy_file "$TEMPLATE_ROOT/core/mcp/.mcp.json.template" "$TARGET_ROOT/.mcp.json.suggested"
  render_template "$TEMPLATE_ROOT/core/commands/mcp-discover.md" "$TARGET_ROOT/.agent/commands/mcp-discover.md"

  if [ "$features" = "full" ] && [ "$harness" = "codex" ]; then
    _mcp_skill_dest="$TARGET_ROOT/.agents/skills/agent-bootstrap/agent-mcp-discover/SKILL.md"
    if [ -e "$_mcp_skill_dest" ] && [ "$force" != "1" ]; then
      log "SKIP existing $_mcp_skill_dest"
      record_skipped "$_mcp_skill_dest"
    else
      ensure_dir "$(dirname "$_mcp_skill_dest")"
      if [ "$dry_run" = "1" ]; then
        log "DRY-RUN write $_mcp_skill_dest"
      else
        cat > "$_mcp_skill_dest" <<'EOF'
---
name: agent-mcp-discover
description: Use when the user invokes Agent Bootstrap command mcp-discover, agent:mcp-discover, or asks Codex to recommend MCP servers for this repository.
---

# Agent Bootstrap mcp-discover Command

This is a Codex wrapper skill for the canonical command file.

1. Read `.agent/commands/mcp-discover.md`.
2. Treat the user's current request, including any text after `agent-mcp-discover` or `agent:mcp-discover`, as the command arguments or task context.
3. Follow `.agent/commands/mcp-discover.md` exactly.
4. Keep `.agent/commands/mcp-discover.md` as the source of truth; do not edit this wrapper when changing command behavior.
EOF
      fi
      record_written "$_mcp_skill_dest"
    fi
  fi
}
