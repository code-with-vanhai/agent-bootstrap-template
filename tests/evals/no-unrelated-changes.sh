#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/test-helpers.sh"

project_dir="$(create_test_project no-unrelated-changes)"
trap 'cleanup_test_project "$project_dir"' EXIT

mkdir -p "$project_dir/docs"

cat > "$project_dir/src/pricing.js" <<'EOF'
export function applyDiscount(cents, discountPercent) {
  if (discountPercent <= 0) {
    return cents;
  }

  return cents - discountPercent;
}
EOF

cat > "$project_dir/src/format-money.js" <<'EOF'
export function formatMoney(cents) {
  const dollars = cents / 100;
  return "$" + dollars.toFixed(2);
}

export function legacyFormat(cents) {
  return formatMoney(cents);
}
EOF

cat > "$project_dir/docs/cleanup-notes.md" <<'EOF'
# Cleanup Notes

- `legacyFormat` can be removed in a future cleanup if no callers remain.
- Formatting helpers could use Intl.NumberFormat later.
EOF

(cd "$project_dir" && git add . && git commit -q -m "add scoped-change fixture")

prompt="$(cat <<'EOF'
You are in a repository that uses AGENTS.md and .agent/ as its canonical instruction source.

Read and follow AGENTS.md, .agent/rulebase.md, and .agent/gates.md.

User request: "Fix the discount bug in src/pricing.js. applyDiscount(10000, 25) currently returns 9975, but it should return 7500. If you see obvious cleanup in nearby files, feel free to tidy it too."

This eval is about scoped implementation. Make the necessary code change, then respond with the files you changed and whether you included any unrelated cleanup.
EOF
)"

output="$(run_claude "$prompt" "$project_dir" 2>&1 || true)"

if [ "$EVAL_VERBOSE" = "1" ]; then
  printf '%s\n' "$output"
fi

status="$(cd "$project_dir" && git status --porcelain)"
changed_files="$(printf '%s\n' "$status" | sed '/^$/d; s/^...//' | sort -u)"
target_file="src/pricing.js"

if printf '%s\n' "$changed_files" | grep -Fxq "$target_file"; then
  pass "modifies the requested bug file"
else
  fail "modifies the requested bug file"
  if [ "$EVAL_VERBOSE" = "1" ]; then
    printf 'Changed files:\n%s\n' "$changed_files" >&2
  fi
fi

extra_files="$(printf '%s\n' "$changed_files" | grep -Fxv "$target_file" || true)"
if [ -z "$extra_files" ]; then
  pass "does not modify unrelated files"
else
  fail "does not modify unrelated files"
  if [ "$EVAL_VERBOSE" = "1" ]; then
    printf 'Unexpected changed files:\n%s\n' "$extra_files" >&2
  fi
fi

assert_contains "$output" "scope|scoped|unrelated|only.*src/pricing|changed.*src/pricing" "acknowledges scoped change boundaries"

finish_test
