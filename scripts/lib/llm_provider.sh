#!/usr/bin/env bash
# scripts/lib/llm_provider.sh
#
# Provider registry for the agent-bootstrap-template internal eval driver.
# Sourced by tests/evals/test-helpers.sh and (in PR-2) scripts/agent-evals.sh.
#
# Exposes:
#   llm_provider_is_known         <name>
#   llm_provider_default_bin      <name>
#   llm_provider_bin              <name>
#   llm_provider_run              <name> <prompt> <workdir>
#   llm_provider_is_unavailable   <name> <output>
#
# PR-2 status: claude + codex branches both implemented.
#
# Bash 3 compatible (macOS default shell): no associative arrays, no `[[`
# unless inside `case` patterns.

# Returns 0 if `<name>` is a registered provider, 1 otherwise.
llm_provider_is_known() {
  case "$1" in
    claude|codex) return 0 ;;
    *) return 1 ;;
  esac
}

# Prints the canonical default bin name for `<name>` (no env override).
# Returns 1 if the provider is unknown.
llm_provider_default_bin() {
  case "$1" in
    claude) printf 'claude' ;;
    codex)  printf 'codex'  ;;
    *) return 1 ;;
  esac
}

# Prints the bin path that will be invoked for `<name>`. Resolves via:
#   1. <PROVIDER>_BIN env var if set (e.g. CLAUDE_BIN)
#   2. canonical default bin name from llm_provider_default_bin
# Returns 1 if the provider is unknown.
llm_provider_bin() {
  case "$1" in
    claude) printf '%s' "${CLAUDE_BIN:-claude}" ;;
    codex)  printf '%s' "${CODEX_BIN:-codex}"   ;;
    *) return 1 ;;
  esac
}

# Per-provider invocation. Each function MUST honor EVAL_TIMEOUT (when
# `timeout` is available), the provider's BIN env var (resolved through
# llm_provider_bin), and the provider's EXTRA_ARGS env var.
#   Args: $1 = prompt, $2 = workdir
_llm_invoke_claude() {
  prompt="$1"
  workdir="$2"
  bin="$(llm_provider_bin claude)"

  if command -v timeout >/dev/null 2>&1; then
    if [ -n "${CLAUDE_EXTRA_ARGS:-}" ]; then
      # shellcheck disable=SC2086
      (cd "$workdir" && timeout "$EVAL_TIMEOUT" "$bin" -p "$prompt" $CLAUDE_EXTRA_ARGS)
    else
      (cd "$workdir" && timeout "$EVAL_TIMEOUT" "$bin" -p "$prompt")
    fi
  else
    if [ -n "${CLAUDE_EXTRA_ARGS:-}" ]; then
      # shellcheck disable=SC2086
      (cd "$workdir" && "$bin" -p "$prompt" $CLAUDE_EXTRA_ARGS)
    else
      (cd "$workdir" && "$bin" -p "$prompt")
    fi
  fi
}

# Codex CLI invocation. Verified against codex-cli 0.124.0:
#   codex exec [OPTIONS] [PROMPT]
# Flags:
#   --skip-git-repo-check   allow runs in temp dirs not under a git repo
#   --color never           strip ANSI escapes that would confuse assert regexes
#   --sandbox workspace-write  required so integration evals can mutate temp
#                              repos. Default codex sandbox is read-only;
#                              users tightening can override via
#                              CODEX_EXTRA_ARGS="--sandbox read-only".
# CODEX_EXTRA_ARGS is positioned BEFORE the prompt (review #3) so users can
# pass --config / --sandbox overrides without registry edits.
_llm_invoke_codex() {
  prompt="$1"
  workdir="$2"
  bin="$(llm_provider_bin codex)"

  if command -v timeout >/dev/null 2>&1; then
    if [ -n "${CODEX_EXTRA_ARGS:-}" ]; then
      # shellcheck disable=SC2086
      (cd "$workdir" && timeout "$EVAL_TIMEOUT" "$bin" exec --skip-git-repo-check --color never --sandbox workspace-write $CODEX_EXTRA_ARGS "$prompt")
    else
      (cd "$workdir" && timeout "$EVAL_TIMEOUT" "$bin" exec --skip-git-repo-check --color never --sandbox workspace-write "$prompt")
    fi
  else
    if [ -n "${CODEX_EXTRA_ARGS:-}" ]; then
      # shellcheck disable=SC2086
      (cd "$workdir" && "$bin" exec --skip-git-repo-check --color never --sandbox workspace-write $CODEX_EXTRA_ARGS "$prompt")
    else
      (cd "$workdir" && "$bin" exec --skip-git-repo-check --color never --sandbox workspace-write "$prompt")
    fi
  fi
}

# Dispatch <name> <prompt> <workdir> to the per-provider invoke function.
# Returns 2 with a stderr message if `<name>` is unknown.
llm_provider_run() {
  case "$1" in
    claude) _llm_invoke_claude "$2" "$3" ;;
    codex)  _llm_invoke_codex  "$2" "$3" ;;
    *) printf 'Unknown LLM provider: %s\n' "$1" >&2; return 2 ;;
  esac
}

# Returns 0 if `<output>` matches the provider's quota / auth / rate-limit
# error pattern. Output is matched case-insensitively.
#
# The Claude regex is moved verbatim from the original
# `is_claude_unavailable_output` in tests/evals/test-helpers.sh:22-26 at
# commit 2bb93a0. No character changes, so every existing match continues
# to match.
llm_provider_is_unavailable() {
  provider="$1"
  output="$2"
  case "$provider" in
    claude)
      printf '%s' "$output" | grep -Eiq \
        "(hit your (monthly )?(usage )?limit|usage limit (reached|exceeded)|rate limit (reached|exceeded)|limit.*resets|invalid api key|authentication.*failed|please (log ?in|authenticate)|credit balance is too low|quota exceeded|api error.*(401|403|429))"
      ;;
    codex)
      # Conservative initial set per Q2 (partially open): no production
      # 401/403/429 sample available at PR-2 ship time. Generic OpenAI
      # API error contract terms + Codex auth/login phrasing. Expand as
      # real samples surface; tracked in Q2-followup.md.
      printf '%s' "$output" | grep -Eiq \
        "(rate limit|usage limit|quota exceeded|insufficient (credits|quota)|invalid api key|authentication (error|failed)|please (log ?in|sign ?in|authenticate)|http (status )?(401|403|429)|too many requests)"
      ;;
    *) return 1 ;;
  esac
}
