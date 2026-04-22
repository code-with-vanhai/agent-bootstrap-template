# Behavior Evals

These evals run real headless agent sessions to check whether the generated instructions shape behavior, not just file structure.

They are intentionally separate from `scripts/agent-validate.sh`:

- `agent-validate.sh` checks files, placeholders, syntax, and required content.
- `agent-evals.sh` invokes `claude -p` and may consume model tokens.

## Running

```bash
scripts/agent-evals.sh --fast
scripts/agent-evals.sh --integration
```

Options:

- `--fast`: run fast evals only. This is the default.
- `--integration`: run fast evals plus slower integration evals.
- `--timeout <sec>`: per-eval timeout, default `300`.
- `--verbose`: print full agent output on assertion failures.
- `--skip-on-missing-cli`: exit 0 with `SKIP` when `claude` is not installed. This is the default behavior.

## Cost And Flakiness

Behavior evals can cost money because they call the Claude CLI. They may also be sensitive to model and harness changes. Use broad regex assertions and keep prompts focused.

Do not wire these into CI unless the repo owner explicitly accepts the cost and flakiness tradeoff.

## Included Evals

Fast evals:

- `verify-before-claim.sh`: rejects completion claims without fresh verification evidence.
- `root-cause-first.sh`: starts bugfix work with root-cause investigation.
- `no-invented-gates.sh`: refuses to invent conventional test commands when gates are not configured.

Integration evals:

- `no-unrelated-changes.sh`: verifies the agent edits only the requested bug file when offered tempting cleanup.
- `bootstrap-pending-completion.sh`: verifies script-first bootstrap can be completed by the agent and pass generated validation.

## Adding Evals

1. Add a shell script under `tests/evals/`.
2. Source `tests/evals/test-helpers.sh`.
3. Use `create_test_project` for a temporary repo with minimal `.agent/` files.
4. Use `run_claude` to execute the prompt.
5. Assert both required behavior and forbidden behavior.
6. Add the script to `scripts/agent-evals.sh`.
