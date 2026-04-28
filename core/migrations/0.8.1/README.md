# Migration: 0.8.0 -> 0.8.1

## Source Acceptance

This migration accepts only `0.8.0` as a source version.

Repos on earlier versions must sync one release at a time.

## What This Migration Ships

0.8.1 is a patch release for the generated agent-system validator.

It updates downstream generated repos with:

- `scripts/lib/validate_agent_system.py` marker scanning that is limited to
  generated text surfaces (`.agent/`, tool adapters, and `.github/`);
- binary/cache-file filtering for generated text scans.

The fix prevents post-bootstrap generated repos from failing validation because
the validator source, or Python bytecode cache, contains the bootstrap completion
marker literal.

## Verification

`tests/migrations/0.8.1/run.sh` builds a 0.8.0-shaped fixture, reproduces the
old validator false positive, applies 0.8.1, asserts the new manifest values and
validator content, and checks that generated validation passes.
