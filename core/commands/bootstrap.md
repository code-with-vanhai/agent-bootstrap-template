---
description: Bootstrap Agent Bootstrap Kit into the current repository using the deterministic script-first flow.
argument-hint: [bootstrap-request.sh flags]
---

# Bootstrap Agent System

Use this command from the target repository.

Precondition: this command must run in the target repository, not in the `agent-bootstrap-template` source repository. If the current working directory is the template itself, or contains `.claude-plugin/plugin.json` declaring `"name": "agent-bootstrap"`, stop and ask the user to run the command from the target repository.

Task: $ARGUMENTS

If invoked as `agent:bootstrap <flags>` in a non-Claude harness, treat the text after `agent:bootstrap` as bootstrap flags for this task.

Supported bootstrap flags for this command are `--features minimal|standard|full`, `--install-hook`, `--force`, and `--dry-run`. Keep `--target .` unless the user explicitly supplies a different target. Do not pass `--template` or `--harness` through this command unless the user is intentionally overriding the plugin wrapper behavior.

If `.agent/bootstrap-pending.md` already exists:

1. Do not run bootstrap again.
2. Complete `.agent/bootstrap-pending.md`.
3. Scan checked-in files before filling repo facts.
4. Run `bash scripts/agent-validate.sh`.
5. Delete `.agent/bootstrap-pending.md` only after validation passes.

If `.agent/` exists without `.agent/bootstrap-pending.md`:

1. Inspect the existing generated system.
2. Do not overwrite it unless the user explicitly asks for `--force`.
3. Prefer reporting the current state and asking for the intended migration or refresh.

If `.agent/bootstrap-pending.md` does not exist:

1. Run the plugin wrapper from the target repository.
2. Start with this command:

```bash
agent-bootstrap --features standard --target .
```

3. If the invocation included supported bootstrap flags, apply them to the command. For example, `--features full` should produce `agent-bootstrap --features full --target .`.
4. Use `--features full` only when the user wants native skills and the optional worktree workflow.
5. Do not add `--install-hook` unless the user explicitly asks for SessionStart context injection.
6. After the script creates `.agent/bootstrap-pending.md`, complete the pending tasks.

Hard rule: do not hand-create the `.agent/` skeleton. The deterministic script owns skeleton generation; the agent owns repo-specific completion.
