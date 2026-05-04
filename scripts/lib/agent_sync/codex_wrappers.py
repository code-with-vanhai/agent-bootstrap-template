"""Codex command-wrapper SKILL.md generator.

When a migration declares ``generate_codex_command_wrappers`` and the
target has the matching ``features_enabled`` flag, this module emits one
``SKILL.md`` per command file under the configured ``target_dir``. Each
wrapper is a thin pointer back to the canonical ``.agent/commands/<x>.md``
so editing the canonical file does not require regenerating the wrapper.
"""

from __future__ import annotations

from pathlib import Path

from .errors import ConflictError
from .io_utils import read_bytes, rel_path
from .migrations import list_tag_files


def command_wrapper(command_name):
    skill_name = f"agent-{command_name}"
    return f"""---
name: {skill_name}
description: Use when the user invokes Agent Bootstrap command {skill_name}, agent:{command_name}, or asks Codex to run the {command_name} agent workflow.
---

# Agent Bootstrap {command_name} Command

This is a Codex wrapper skill for the canonical command file.

1. Read `.agent/commands/{command_name}.md`.
2. Treat the user's current request, including any text after `{skill_name}` or `agent:{command_name}`, as the command arguments or task context.
3. Follow `.agent/commands/{command_name}.md` exactly.
4. Keep `.agent/commands/{command_name}.md` as the source of truth; do not edit this wrapper when changing command behavior.
""".encode("utf-8")


def plan_codex_wrappers(
    template_root, target, migration, manifest, accept_theirs, writes, updated, accepted
):
    generator = migration.get("generate_codex_command_wrappers") or {}
    if not generator:
        return
    feature = generator.get("enabled_when_feature_present")
    features = manifest.get("features_enabled") or []
    if feature not in features:
        return

    target_dir = rel_path(generator["target_dir"])
    for source_path in list_tag_files(
        template_root, migration["to"], generator["commands_source_glob"]
    ):
        command_name = Path(source_path).stem
        target_rel = (
            Path(target_dir) / f"agent-{command_name}" / "SKILL.md"
        ).as_posix()
        theirs = command_wrapper(command_name)
        ours = read_bytes(target / target_rel)
        if ours == theirs:
            continue
        if ours is None:
            writes[target_rel] = theirs
            updated.append(target_rel)
            continue
        if target_rel in accept_theirs:
            writes[target_rel] = theirs
            accepted.append(target_rel)
            updated.append(target_rel)
            continue
        raise ConflictError(
            f"generated Codex wrapper already exists with different content: {target_rel}"
        )
