# Bugfix Workflow

Use this workflow for defects, regressions, failed tests, incidents, or incorrect behavior.

## Steps

1. Reproduce or narrow the bug.
2. Identify expected vs actual behavior.
3. Locate the subsystem and owner.
4. Find the smallest root-cause fix.
5. Add a regression test when practical.
6. Run the narrowest gate that proves the fix.
7. If the bug reveals a durable rule, update `lessons.md`.

## Multi-Agent Coordination

When another agent may be working in the same files, use
`scripts/agent-lock.sh run --paths '<glob>' --task '<summary>' -- <command>`
around the bugfix command. The lock is advisory and prevents accidental overlap;
it does not replace ownership review or verification.

## Root Cause Standard

A bugfix should explain:

- What failed.
- Why it failed.
- Why the patch fixes that cause.
- What test or gate prevents recurrence.

## Do Not

- Do not mask symptoms by weakening validation, auth, error handling, or tests.
- Do not broaden the fix into unrelated refactors.
- Do not delete failing tests unless they are demonstrably invalid and replaced.
