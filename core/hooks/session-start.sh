#!/usr/bin/env bash
set -euo pipefail

# Optional SessionStart hook template for harnesses that support context injection.
# This script is off by default. Copy it into the target harness hook location only
# when the project intentionally wants rulebase reminders injected at session start.

if [ -n "${AGENT_ROOT:-}" ]; then
  ROOT="$AGENT_ROOT"
elif [ -d ".agent" ]; then
  ROOT="$(pwd)"
else
  ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
fi

rulebase_path="$ROOT/.agent/rulebase.md"
gates_path="$ROOT/.agent/gates.md"

if [ ! -f "$rulebase_path" ]; then
  exit 0
fi

escape_for_json() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"
  s="${s//$'\r'/\\r}"
  s="${s//$'\t'/\\t}"
  printf '%s' "$s"
}

rulebase_content="$(sed -n '1,220p' "$rulebase_path")"
gates_reminder=""
if [ -f "$gates_path" ]; then
  gates_reminder="$(sed -n '1,80p' "$gates_path")"
fi

context="<IMPORTANT_AGENT_RULES>
This repository uses .agent/ as the canonical agent instruction source.

For any coding task, MUST re-read .agent/rulebase.md before planning or editing.

Rulebase excerpt:
$rulebase_content

Gates excerpt:
$gates_reminder
</IMPORTANT_AGENT_RULES>"

context_escaped="$(escape_for_json "$context")"

if [ -n "${CURSOR_PLUGIN_ROOT:-}" ]; then
  printf '{\n  "additional_context": "%s"\n}\n' "$context_escaped"
elif [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
  printf '{\n  "hookSpecificOutput": {\n    "hookEventName": "SessionStart",\n    "additionalContext": "%s"\n  }\n}\n' "$context_escaped"
else
  printf '{\n  "additionalContext": "%s"\n}\n' "$context_escaped"
fi
