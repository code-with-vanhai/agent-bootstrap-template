# Behavior Evals

These evals run real headless agent sessions to check whether the generated
instructions shape behavior, not just file structure.

They are intentionally separate from `scripts/agent-validate.sh`:

- `agent-validate.sh` checks files, placeholders, syntax, and required content.
- `agent-evals.sh` invokes a headless LLM CLI (`claude` or `codex`) and may consume model tokens.

## Provider selection

Since 0.5.0 the eval runner is provider-agnostic. The active LLM provider is
chosen by, in precedence order:

1. The `--provider <name>` CLI flag (highest precedence).
2. The `AGENT_LLM_PROVIDER` environment variable.
3. The default value `claude` (lowest precedence; matches 0.4.0 behavior).

Known providers are `claude` and `codex`. Unknown values fail fast with
`Unknown LLM provider: <name>` and exit code 2.

```bash
# Default (Claude Code CLI):
scripts/agent-evals.sh --fast

# Explicit Codex:
scripts/agent-evals.sh --fast --provider codex
AGENT_LLM_PROVIDER=codex scripts/agent-evals.sh --fast
```

`--provider` beats env, so `AGENT_LLM_PROVIDER=codex scripts/agent-evals.sh --provider claude`
runs the Claude path.

## Running

```bash
scripts/agent-evals.sh --fast            # default mode; deterministic, token-free
scripts/agent-evals.sh --behavior        # LLM-driven advisory evals (consumes quota)
scripts/agent-evals.sh --integration     # all known evals (heaviest)
```

Options:

- `--fast`: deterministic evals only. Default. Safe to run on every commit / in CI without LLM credentials.
- `--behavior`: LLM-driven advisory evals. Each run consumes provider quota. Results are advisory, NOT a release gate.
- `--integration`: deterministic + behavior + integration evals. Heaviest mode.
- `--provider <claude|codex>`: pick a provider for this run.
- `--timeout <sec>`: per-eval timeout, default `300`.
- `--artifact-dir <path>`: persist per-eval `metadata.json`, `output.txt`,
  and prompt snapshots when an eval calls `run_llm`. This overrides
  `EVAL_ARTIFACT_DIR` when both are set.
- `--verbose`: print full agent output on assertion failures.

## Per-provider env vars

| Provider | Bin override | Extra args | Notes |
|---|---|---|---|
| `claude` | `CLAUDE_BIN` (default `claude`) | `CLAUDE_EXTRA_ARGS` | Some Claude CLI versions require explicit tool permissions. |
| `codex`  | `CODEX_BIN`  (default `codex`)  | `CODEX_EXTRA_ARGS`  | The runner invokes `codex exec --skip-git-repo-check --color never --sandbox workspace-write [CODEX_EXTRA_ARGS] <prompt>`. Override the sandbox via `CODEX_EXTRA_ARGS="--sandbox read-only"` when needed. |

```bash
# Claude with explicit tool permissions:
CLAUDE_EXTRA_ARGS="--allowedTools Bash,Read,Edit,Write" scripts/agent-evals.sh --integration

# Codex with read-only sandbox override:
CODEX_EXTRA_ARGS="--sandbox read-only" scripts/agent-evals.sh --behavior --provider codex
```

Relative `CLAUDE_BIN` / `CODEX_BIN` paths (e.g. `tests/evals/mocks/claude-quota.sh`)
are normalized to absolute against the repo root before being exported to eval
children, so they keep working even when an eval helper `cd`s into a temp project
dir before exec.

## SKIP / FAIL classification

The runner distinguishes:

- exit `0`: PASS.
- exit `77`: SKIP (per-eval; e.g. provider CLI missing, quota exhausted, auth failure).
- other: FAIL.

When the active provider's CLI is missing, the runner prints
`SKIP: <provider> CLI not found; LLM-driven evals were not run.` and exits 0.
When the CLI exits with a quota / rate-limit / auth error matching the
provider's regex, the affected eval prints
`SKIP: <provider> CLI unavailable (quota/auth): <first line>` (exit 77) instead
of asserting against the error string and reporting a false FAIL.

When LLM evals produce assertion failures, the runner prints
`LLM-driven evals are advisory; do NOT block release on this alone.` to prevent
downstream consumers from misreading flaky LLM output as a release-broken signal.

## Cost And Flakiness

Behavior evals can cost money because they call the LLM CLI. They may also be
sensitive to model and harness changes. Use broad regex assertions and keep
prompts focused.

Do not wire these into CI unless the repo owner explicitly accepts the cost
and flakiness tradeoff.

## Artifacts

Use `--artifact-dir <path>` or `EVAL_ARTIFACT_DIR=<path>` to persist eval
debugging artifacts. CLI flag precedence wins over the environment variable.
Each selected eval gets its own directory with:

- `metadata.json`: eval name, provider, mode, result classification
  (`PASS`, `SKIP`, or `FAIL`), exit code, timestamps, duration, and whether
  artifact output was truncated.
- `output.txt`: combined stdout/stderr from the eval script.
- `prompt.md`: prompt snapshot when the eval routes through `run_llm`.

Artifact capture is intended for debugging. Behavior eval artifacts can include
model output, so avoid uploading them from credentialed runs unless the repo
owner has accepted that exposure.

## Included Evals

### Deterministic (`--fast`, no LLM call)

- `plugin-command-load.sh`: verifies Claude Code loads plugin commands from the canonical `core/commands/` custom path. Provider-specific: SKIPs cleanly with reason `plugin probe is Claude-Code-specific (provider=<x>)` when `provider != claude` (no Codex equivalent surface).
- `bootstrap-render-fixture.sh`: verifies `bootstrap-request.sh` renders placeholders literally for a temp target path containing spaces and `&`, leaves no placeholders, and writes valid manifest JSON.
- `codex-harness-fixture.sh`: verifies `bootstrap-request.sh --harness codex --features full` produces the expected `.agents/skills/agent-bootstrap/<name>/SKILL.md` tree (7 core skills + 9 generated commands). Pure filesystem check, runs under any provider.
- `security-gate-fixture.sh`: verifies generated `scripts/agent-eval.sh security` reports `not configured` when `gitleaks` is missing and invokes `gitleaks dir .` when a compatible scanner is present.

### Behavior (`--behavior`, LLM-driven, advisory)

- `verify-before-claim.sh`: rejects completion claims without fresh verification evidence.
- `root-cause-first.sh`: starts bugfix work with root-cause investigation.
- `no-invented-gates.sh`: refuses to invent conventional test commands when gates are not configured.
- `plan-grounding.sh`: rejects plans that quote non-existent code or fabricate `BEFORE` snippets.

### Integration (`--integration`, LLM-driven)

- `no-unrelated-changes.sh`: verifies the agent edits only the requested bug file when offered tempting cleanup.
- `bootstrap-pending-completion.sh`: verifies script-first bootstrap can be completed by the agent and pass generated validation.

## Adding Evals

1. Add a shell script under `tests/evals/`.
2. Source `tests/evals/test-helpers.sh`.
3. Use `create_test_project` for a temporary repo with minimal `.agent/` files.
4. Use `run_llm` to execute the prompt (provider-agnostic; reads `AGENT_LLM_PROVIDER`). Use `skip_if_llm_unavailable` to honor the SKIP contract on quota / auth errors.
5. Assert both required behavior and forbidden behavior.
6. Add the script to `scripts/agent-evals.sh`'s deterministic, behavior, or integration array as appropriate.
