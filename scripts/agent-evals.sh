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

usage() {
  cat <<'EOF'
Usage: scripts/agent-evals.sh [--fast|--behavior|--integration] [--provider <name>] [--timeout <sec>] [--verbose] [--skip-on-missing-cli]

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
  "tests/evals/codex-harness-fixture.sh"
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

for eval_script in "${evals[@]}"; do
  if [ ! -x "$eval_script" ]; then
    printf 'SKIP: %s is not present or not executable.\n' "$eval_script"
    skipped=$((skipped + 1))
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
    AGENT_LLM_PROVIDER="$provider" CLAUDE_BIN="$bin" \
      CODEX_BIN="${CODEX_BIN:-codex}" \
      EVAL_TIMEOUT="$timeout_seconds" EVAL_VERBOSE="$verbose" "$eval_script"
  else
    AGENT_LLM_PROVIDER="$provider" CODEX_BIN="$bin" \
      CLAUDE_BIN="${CLAUDE_BIN:-claude}" \
      EVAL_TIMEOUT="$timeout_seconds" EVAL_VERBOSE="$verbose" "$eval_script"
  fi
  rc=$?
  set -e
  case "$rc" in
    0)
      printf 'PASS: %s\n' "$eval_script"
      ;;
    77)
      printf 'SKIP: %s (%s CLI unavailable)\n' "$eval_script" "$provider"
      skipped=$((skipped + 1))
      ;;
    *)
      printf 'FAIL: %s\n' "$eval_script" >&2
      failures=$((failures + 1))
      ;;
  esac
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
  printf '\nEvals (mode=%s): %d skipped (%s CLI unavailable or quota exhausted); remaining passed.\n' "$mode" "$skipped" "$provider"
else
  printf '\nAll selected evals passed (mode=%s).\n' "$mode"
fi
