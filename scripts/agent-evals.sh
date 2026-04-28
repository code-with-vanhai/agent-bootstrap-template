#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

# Source the provider registry. PR-2 added the codex branch; PR-1 had only
# claude. We use llm_provider_is_known / llm_provider_bin for validation
# and bin resolution so this driver carries no provider-specific strings.
# shellcheck source=lib/llm_provider.sh
. "$ROOT/scripts/lib/llm_provider.sh"

mode="fast"
timeout_seconds="300"
verbose="0"
skip_on_missing_cli="1"
provider_cli_override=""
provider="${AGENT_LLM_PROVIDER:-claude}"
artifact_dir="${EVAL_ARTIFACT_DIR:-}"
artifact_dir_cli=""

usage() {
  cat <<'EOF'
Usage: scripts/agent-evals.sh [--fast|--behavior|--integration] [--provider <name>] [--timeout <sec>] [--artifact-dir <path>] [--verbose] [--skip-on-missing-cli]

Runs headless evals for the agent-system template.

Mode semantics:
  --fast         Deterministic, free, reliable evals only (default).
                 No LLM calls. Safe to run on every commit / in CI.
  --behavior     LLM-driven advisory evals (call the configured provider
                 CLI). Inherently flaky; treat as advisory, NOT a release
                 gate. Each run consumes provider quota.
  --integration  All known evals: deterministic + behavior + integration.
                 Heaviest mode; only run intentionally.

Provider selection (highest precedence first):
  --provider <name>      Choose LLM provider explicitly. Known: claude, codex.
  AGENT_LLM_PROVIDER env  Set provider via env (overridden by --provider).
  Default                claude (preserves pre-0.5.0 behavior).

Provider env vars:
  CLAUDE_BIN             Path to claude CLI (default: claude).
  CLAUDE_EXTRA_ARGS      Extra args appended after `-p "$prompt"`.
  CODEX_BIN              Path to codex CLI (default: codex).
  CODEX_EXTRA_ARGS       Extra args inserted BEFORE the prompt in
                         `codex exec --skip-git-repo-check --color never
                         --sandbox workspace-write $CODEX_EXTRA_ARGS "$prompt"`.

Other options:
  --timeout <sec>        Per-eval timeout in seconds (default: 300).
  --artifact-dir <path>  Persist per-eval output and metadata. Overrides
                         EVAL_ARTIFACT_DIR when both are set.
  --verbose              Show full provider output from each eval.
  --skip-on-missing-cli  Exit 0 with SKIP if the provider CLI is missing
                         (default).
  -h, --help             Show this help.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --fast)
      mode="fast"
      shift
      ;;
    --behavior)
      mode="behavior"
      shift
      ;;
    --integration)
      mode="integration"
      shift
      ;;
    --timeout)
      if [ "$#" -lt 2 ]; then
        printf 'Missing value for --timeout\n' >&2
        exit 2
      fi
      timeout_seconds="$2"
      shift 2
      ;;
    --verbose)
      verbose="1"
      shift
      ;;
    --artifact-dir)
      if [ "$#" -lt 2 ]; then
        printf 'Missing value for --artifact-dir\n' >&2
        exit 2
      fi
      artifact_dir_cli="$2"
      shift 2
      ;;
    --skip-on-missing-cli)
      skip_on_missing_cli="1"
      shift
      ;;
    --provider)
      if [ "$#" -lt 2 ]; then
        printf 'Missing value for --provider\n' >&2
        exit 2
      fi
      provider_cli_override="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ -n "$artifact_dir_cli" ]; then
  artifact_dir="$artifact_dir_cli"
fi

# Resolve final provider: explicit --provider wins over AGENT_LLM_PROVIDER
# env, which wins over the claude default (already set above). Validate
# through the provider registry so unknown values are rejected here, not
# silently downstream.
if [ -n "$provider_cli_override" ]; then
  provider="$provider_cli_override"
fi

if ! llm_provider_is_known "$provider"; then
  printf 'Unknown LLM provider: %s\n' "$provider" >&2
  printf 'Try --help for the list of known providers.\n' >&2
  exit 2
fi

bin="$(llm_provider_bin "$provider")"

# Normalize a relative-with-slash bin path to absolute. Required because
# eval helpers cd into temp project dirs before exec; without this a
# relative `CLAUDE_BIN=tests/evals/mocks/claude-quota.sh` (or the codex
# equivalent) resolves at the repo-root precheck below but then ENOENTs
# when the eval child cds away. A bare-name bin (no slash) is left alone
# so PATH lookup still works.
case "$bin" in
  /*) ;;
  */*) bin="$ROOT/$bin" ;;
esac

# Deterministic evals: no LLM calls, free, reliable. Safe in --fast / CI.
deterministic_evals=(
  "tests/evals/plugin-command-load.sh"
  "tests/evals/bootstrap-render-fixture.sh"
  "tests/evals/codex-harness-fixture.sh"
  "tests/evals/security-gate-fixture.sh"
)

# Behavior evals: LLM-driven, advisory only. Each run costs Claude quota and
# is non-deterministic. Demoted out of --fast so a flaky LLM run does not
# masquerade as a release-gate failure.
behavior_evals=(
  "tests/evals/verify-before-claim.sh"
  "tests/evals/root-cause-first.sh"
  "tests/evals/no-invented-gates.sh"
  "tests/evals/plan-grounding.sh"
)

# Integration evals: also LLM-driven, advisory.
integration_evals=(
  "tests/evals/no-unrelated-changes.sh"
  "tests/evals/bootstrap-pending-completion.sh"
)

case "$mode" in
  fast)
    evals=("${deterministic_evals[@]}")
    needs_provider=0
    ;;
  behavior)
    evals=("${behavior_evals[@]}")
    needs_provider=1
    ;;
  integration)
    evals=("${deterministic_evals[@]}" "${behavior_evals[@]}" "${integration_evals[@]}")
    needs_provider=1
    ;;
  *)
    printf 'Internal error: unknown mode %q\n' "$mode" >&2
    exit 2
    ;;
esac

if [ "$needs_provider" = "1" ] && ! command -v "$bin" >/dev/null 2>&1; then
  if [ "$skip_on_missing_cli" = "1" ]; then
    printf 'SKIP: %s CLI not found; LLM-driven evals were not run.\n' "$provider"
    exit 0
  fi
  printf 'FAIL: %s CLI not found.\n' "$provider" >&2
  exit 1
fi

failures=0
skipped=0
artifact_cap_bytes=$((20 * 1024 * 1024))

artifact_safe_name() {
  printf '%s' "$1" | tr '/ ' '__' | tr -c 'A-Za-z0-9_.-' '_'
}

artifact_dir_size() {
  dir="$1"
  if command -v du >/dev/null 2>&1; then
    du -sk "$dir" | awk '{print $1 * 1024}'
  else
    printf '0'
  fi
}

write_artifact_metadata() {
  metadata_file="$1"
  eval_script="$2"
  classification="$3"
  rc="$4"
  started_at="$5"
  ended_at="$6"
  duration_seconds="$7"
  truncated="$8"

  META_EVAL="$eval_script" \
  META_PROVIDER="$provider" \
  META_MODE="$mode" \
  META_CLASSIFICATION="$classification" \
  META_EXIT_CODE="$rc" \
  META_STARTED_AT="$started_at" \
  META_ENDED_AT="$ended_at" \
  META_DURATION_SECONDS="$duration_seconds" \
  META_ARTIFACT_TRUNCATED="$truncated" \
  python3 - "$metadata_file" <<'PY'
import json
import os
import sys

metadata = {
    "eval": os.environ["META_EVAL"],
    "provider": os.environ["META_PROVIDER"],
    "mode": os.environ["META_MODE"],
    "classification": os.environ["META_CLASSIFICATION"],
    "exit_code": int(os.environ["META_EXIT_CODE"]),
    "started_at": os.environ["META_STARTED_AT"],
    "ended_at": os.environ["META_ENDED_AT"],
    "duration_seconds": int(os.environ["META_DURATION_SECONDS"]),
    "artifact_truncated": os.environ["META_ARTIFACT_TRUNCATED"].lower() == "true",
}
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump(metadata, fh, indent=2, sort_keys=True)
    fh.write("\n")
PY
}

for eval_script in "${evals[@]}"; do
  eval_artifact_dir=""
  output_file=""
  metadata_file=""
  started_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  start_epoch="$(date -u +%s)"
  artifact_truncated="false"
  if [ -n "$artifact_dir" ]; then
    eval_artifact_dir="$artifact_dir/$(artifact_safe_name "$eval_script")"
    mkdir -p "$eval_artifact_dir"
    output_file="$eval_artifact_dir/output.txt"
    metadata_file="$eval_artifact_dir/metadata.json"
  fi

  if [ ! -x "$eval_script" ]; then
    printf 'SKIP: %s is not present or not executable.\n' "$eval_script"
    skipped=$((skipped + 1))
    if [ -n "$artifact_dir" ]; then
      ended_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
      end_epoch="$(date -u +%s)"
      printf 'SKIP: %s is not present or not executable.\n' "$eval_script" >"$output_file"
      write_artifact_metadata "$metadata_file" "$eval_script" "SKIP" "77" "$started_at" "$ended_at" "$((end_epoch - start_epoch))" "$artifact_truncated"
    fi
    continue
  fi

  printf '\n>>> %s\n' "$eval_script"
  set +e
  # Pass AGENT_LLM_PROVIDER so run_llm inside the eval dispatches to the
  # right provider. Continue passing CLAUDE_BIN for back-compat (eval
  # scripts that read it directly) and add CODEX_BIN for symmetry. The
  # provider-resolved $bin is reflected back into the matching env var so
  # an explicit --provider flag override is honored even if the user only
  # set the OTHER provider's BIN.
  if [ "$provider" = "claude" ]; then
    if [ -n "$artifact_dir" ]; then
      AGENT_LLM_PROVIDER="$provider" CLAUDE_BIN="$bin" \
        CODEX_BIN="${CODEX_BIN:-codex}" \
        EVAL_TIMEOUT="$timeout_seconds" EVAL_VERBOSE="$verbose" \
        EVAL_CURRENT_ARTIFACT_DIR="$eval_artifact_dir" "$eval_script" >"$output_file" 2>&1
    else
      AGENT_LLM_PROVIDER="$provider" CLAUDE_BIN="$bin" \
        CODEX_BIN="${CODEX_BIN:-codex}" \
        EVAL_TIMEOUT="$timeout_seconds" EVAL_VERBOSE="$verbose" "$eval_script"
    fi
  else
    if [ -n "$artifact_dir" ]; then
      AGENT_LLM_PROVIDER="$provider" CODEX_BIN="$bin" \
        CLAUDE_BIN="${CLAUDE_BIN:-claude}" \
        EVAL_TIMEOUT="$timeout_seconds" EVAL_VERBOSE="$verbose" \
        EVAL_CURRENT_ARTIFACT_DIR="$eval_artifact_dir" "$eval_script" >"$output_file" 2>&1
    else
      AGENT_LLM_PROVIDER="$provider" CODEX_BIN="$bin" \
        CLAUDE_BIN="${CLAUDE_BIN:-claude}" \
        EVAL_TIMEOUT="$timeout_seconds" EVAL_VERBOSE="$verbose" "$eval_script"
    fi
  fi
  rc=$?
  set -e
  if [ -n "$artifact_dir" ]; then
    cat "$output_file"
    dir_size="$(artifact_dir_size "$eval_artifact_dir")"
    if [ "$dir_size" -gt "$artifact_cap_bytes" ]; then
      artifact_truncated="true"
      if [ -f "$output_file" ]; then
        head -c "$artifact_cap_bytes" "$output_file" >"$output_file.tmp"
        mv "$output_file.tmp" "$output_file"
      fi
    fi
  fi
  case "$rc" in
    0)
      printf 'PASS: %s\n' "$eval_script"
      classification="PASS"
      ;;
    77)
      printf 'SKIP: %s (see eval output above for reason; common causes: %s CLI unavailable, quota/auth, or eval is provider-incompatible)\n' "$eval_script" "$provider"
      skipped=$((skipped + 1))
      classification="SKIP"
      ;;
    *)
      printf 'FAIL: %s\n' "$eval_script" >&2
      failures=$((failures + 1))
      classification="FAIL"
      ;;
  esac
  if [ -n "$artifact_dir" ]; then
    ended_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    end_epoch="$(date -u +%s)"
    write_artifact_metadata "$metadata_file" "$eval_script" "$classification" "$rc" "$started_at" "$ended_at" "$((end_epoch - start_epoch))" "$artifact_truncated"
  fi
done

if [ "$failures" -gt 0 ]; then
  if [ "$mode" = "behavior" ] || [ "$mode" = "integration" ]; then
    printf '\n%d eval(s) failed in mode=%s. LLM-driven evals are advisory; do NOT block release on this alone.\n' "$failures" "$mode" >&2
  else
    printf '\n%d eval(s) failed in mode=%s.\n' "$failures" "$mode" >&2
  fi
  exit 1
fi

if [ "$skipped" -gt 0 ]; then
  printf '\nEvals (mode=%s): %d skipped (see per-eval reasons above; provider=%s); remaining passed.\n' "$mode" "$skipped" "$provider"
else
  printf '\nAll selected evals passed (mode=%s).\n' "$mode"
fi
