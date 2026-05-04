#!/usr/bin/env bash
# Stage 5 deterministic eval: --with-mcp-discovery is a real opt-in toggle.
#
# Asserts:
#   1. Default bootstrap (no flag) creates NO .mcp.json* and NO mcp-discover
#      command file. Existing repos must keep their byte-identical output.
#   2. Bootstrap with --with-mcp-discovery creates .mcp.json.suggested,
#      .agent/commands/mcp-discover.md, the mcp-discovery-suggested feature
#      flag in the manifest, and the suggestion mention in
#      .agent/bootstrap-pending.md.
#   3. The opt-in suggested file passes scripts/lib/validate_mcp_config.py.
#   4. A hand-injected inline GitHub PAT in .mcp.json fails the validator.
#
# This eval invokes NO LLM CLI. It runs in --fast mode.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=tests/evals/test-helpers.sh
source "$SCRIPT_DIR/test-helpers.sh"

default_dir="$(mktemp -d "/tmp/mcp-default-fixture.XXXXXX")"
optin_dir="$(mktemp -d "/tmp/mcp-optin-fixture.XXXXXX")"
trap 'rm -rf "$default_dir" "$optin_dir"' EXIT

# --- Default bootstrap: must not create any MCP files -----------------------
"$ROOT/scripts/bootstrap-request.sh" \
  --target "$default_dir" \
  --features standard \
  --harness generic \
  >/dev/null 2>&1

if [ -e "$default_dir/.mcp.json" ] || [ -e "$default_dir/.mcp.json.suggested" ]; then
  fail "default bootstrap leaves no MCP files in target"
else
  pass "default bootstrap leaves no MCP files in target"
fi

if [ -e "$default_dir/.agent/commands/mcp-discover.md" ]; then
  fail "default bootstrap does not render mcp-discover command"
else
  pass "default bootstrap does not render mcp-discover command"
fi

if grep -q '"mcp-discovery-suggested"' "$default_dir/.agent/manifest.json"; then
  fail "default bootstrap does not enable mcp-discovery-suggested feature"
else
  pass "default bootstrap does not enable mcp-discovery-suggested feature"
fi

# --- Opt-in bootstrap: --with-mcp-discovery emits suggested artifacts -------
"$ROOT/scripts/bootstrap-request.sh" \
  --target "$optin_dir" \
  --features standard \
  --harness generic \
  --with-mcp-discovery \
  >/dev/null 2>&1

if [ -f "$optin_dir/.mcp.json.suggested" ]; then
  pass "opt-in bootstrap renders .mcp.json.suggested"
else
  fail "opt-in bootstrap renders .mcp.json.suggested"
fi

if [ -e "$optin_dir/.mcp.json" ]; then
  fail "opt-in bootstrap does NOT activate .mcp.json"
else
  pass "opt-in bootstrap does NOT activate .mcp.json"
fi

if [ -f "$optin_dir/.agent/commands/mcp-discover.md" ]; then
  pass "opt-in bootstrap renders mcp-discover command"
else
  fail "opt-in bootstrap renders mcp-discover command"
fi

if grep -q '"mcp-discovery-suggested"' "$optin_dir/.agent/manifest.json"; then
  pass "opt-in bootstrap adds mcp-discovery-suggested feature flag"
else
  fail "opt-in bootstrap adds mcp-discovery-suggested feature flag"
fi

if grep -q 'MCP discovery layer:' "$optin_dir/.agent/bootstrap-pending.md"; then
  pass "opt-in bootstrap mentions MCP layer in bootstrap-pending.md"
else
  fail "opt-in bootstrap mentions MCP layer in bootstrap-pending.md"
fi

if [ -f "$optin_dir/scripts/lib/validate_mcp_config.py" ]; then
  pass "opt-in bootstrap copies scripts/lib/validate_mcp_config.py"
else
  fail "opt-in bootstrap copies scripts/lib/validate_mcp_config.py"
fi

if python3 "$ROOT/scripts/lib/validate_mcp_config.py" --root "$optin_dir" >/tmp/mcp-discovery-validate.out 2>&1; then
  pass "validate_mcp_config.py accepts opt-in suggested file"
else
  fail "validate_mcp_config.py accepts opt-in suggested file"
  if [ "${EVAL_VERBOSE:-0}" = "1" ]; then
    cat /tmp/mcp-discovery-validate.out >&2
  fi
fi

# --- Inline-credential rejection regression ---------------------------------
inject_dir="$(mktemp -d "/tmp/mcp-inject-fixture.XXXXXX")"
cat > "$inject_dir/.mcp.json" <<'EOF'
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      }
    }
  }
}
EOF

set +e
python3 "$ROOT/scripts/lib/validate_mcp_config.py" --root "$inject_dir" >/tmp/mcp-discovery-inject.out 2>&1
inject_rc=$?
set -e
rm -rf "$inject_dir"

if [ "$inject_rc" -ne 0 ] && grep -q "inline credential" /tmp/mcp-discovery-inject.out; then
  pass "validate_mcp_config.py rejects inline GitHub PAT"
else
  fail "validate_mcp_config.py rejects inline GitHub PAT"
  if [ "${EVAL_VERBOSE:-0}" = "1" ]; then
    cat /tmp/mcp-discovery-inject.out >&2
  fi
fi

finish_test
