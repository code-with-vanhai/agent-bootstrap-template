#!/usr/bin/env bash
# Stage 4c regression: dry-run stdout/stderr must match the checked-in golden
# fixture after normalizing ephemeral paths (--features full --harness claude).
set -euo pipefail

root="$(git rev-parse --show-toplevel)"
golden="$root/tests/fixtures/bootstrap-dry-run-full-claude.normalized.out"

if [ ! -f "$golden" ]; then
  printf 'FAIL: golden fixture missing: %s\n' "$golden" >&2
  exit 1
fi

work="$(mktemp -d "${TMPDIR:-/tmp}/bootstrap-dry-run-stable.XXXXXX")"
# Canonicalize like bootstrap-request.sh (TARGET_ROOT="$(cd "$target" && pwd)").
# macOS TMPDIR often ends with /; mktemp then yields T//bootstrap-… while
# printed paths use T/bootstrap-…, so sed would miss without this step.
work="$(cd "$work" && pwd)"
got="$(mktemp "${TMPDIR:-/tmp}/bootstrap-dry-run-got.XXXXXX")"

cleanup() {
  rm -rf "$work"
  rm -f "$got"
}
trap cleanup EXIT

"$root/scripts/bootstrap-request.sh" \
  --template "$root" \
  --features full \
  --harness claude \
  --target "$work" \
  --dry-run 2>&1 \
  | sed "s|${work}|@TARGET@|g" \
  | sed "s|${root}|@ROOT@|g" \
  > "$got"

if ! diff -u "$golden" "$got"; then
  printf 'FAIL: bootstrap dry-run output differs from golden.\n' >&2
  printf 'Regenerate with:\n' >&2
  printf '  ROOT="$(git rev-parse --show-toplevel)" && TMP="$(cd "$(mktemp -d)" && pwd)" && \\\n' >&2
  printf '    "$ROOT/scripts/bootstrap-request.sh" --template "$ROOT" --features full --harness claude --target "$TMP" --dry-run 2>&1 \\\n' >&2
  printf '    | sed "s|${TMP}|@TARGET@|g" | sed "s|${ROOT}|@ROOT@|g" \\\n' >&2
  printf '    > "$ROOT/tests/fixtures/bootstrap-dry-run-full-claude.normalized.out"\n' >&2
  exit 1
fi

printf 'PASS: bootstrap dry-run matches golden (--features full --harness claude).\n'
