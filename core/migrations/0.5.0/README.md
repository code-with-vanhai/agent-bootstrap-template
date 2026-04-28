# Migration: 0.4.0 → 0.5.0

## Source acceptance

This migration accepts only `0.4.0` as a source version (`from_versions: ["0.4.0"]`).

**Repos still on 0.3.0 or 0.3.2 must run a two-step upgrade:**

```bash
scripts/agent-sync.sh --target /path/to/repo --to 0.4.0 --apply
scripts/agent-sync.sh --target /path/to/repo --to 0.5.0 --apply
```

`agent-sync.py` is single-step by design (no migration walker). A direct
`agent-sync.sh --to 0.5.0` from a 0.3.x repo will fail with
`migration metadata mismatch: current=0.3.x, requested=0.5.0, ...`. Run
`--to 0.4.0` first.

## What this migration ships

**No downstream content patches.** The 0.5.0 release is a no-op migration
for downstream repo content: both `safe_overwrite` and `patches` arrays are
empty. The only migration-authored mechanical change is the
`manifest_updates` block, which bumps `template_version` and
`synced_to_template_version` to `0.5.0`, records
`synced_to_template_commit` from the `v0.5.0` git tag, and appends a release
note to the manifest's `notes` array.

`agent-sync.py` additionally appends an audit entry to `.agent/sync-log.md`
on every successful apply (independent of the migration manifest contents);
that is normal sync runner behavior, not a migration patch.

## Why no-op

The 0.5.0 release adds an LLM provider abstraction (`AGENT_LLM_PROVIDER`,
`--provider claude|codex`, `CODEX_BIN`, `CODEX_EXTRA_ARGS`) plus a Codex
provider implementation. All the new code lives in **template-tree files**
that downstream repos do **not** receive via bootstrap or sync:

- `scripts/lib/llm_provider.sh` (registry, template-only).
- `scripts/agent-evals.sh`, `tests/evals/test-helpers.sh`, individual eval
  scripts under `tests/evals/` (template-only; downstream repos run evals
  out of this template repo, not their own).
- `tests/evals/codex-harness-fixture.sh` and `tests/evals/mocks/*` (template
  test fixtures, not shipped downstream).

No `.agent/` file's content depends on the new provider abstraction, so
existing repos see no patch.

## Idempotency

Re-running `agent-sync.sh --target <repo> --to 0.5.0 --apply` on an
already-synced repo prints `Target already synced to 0.5.0; no-op.` and
exits 0 without writing.

## Verification

`tests/migrations/0.5.0/run.sh` exercises the migration end-to-end:
builds a genuine 0.4.0 fixture (by syncing a 0.3.0 baseline through 0.4.0
first, then committing), applies `--to 0.5.0`, and asserts the
`git status --short` diff contains exactly `.agent/manifest.json` and
`.agent/sync-log.md` and nothing else. Any third path indicates a
regression of the no-op contract.
