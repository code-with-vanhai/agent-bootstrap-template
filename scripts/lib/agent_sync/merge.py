"""Three-way safe-overwrite planner, write applier, and orphan collector.

The planner is intentionally conservative: it raises
:class:`ConflictError` (printing base/ours/theirs SHAs and inspect
commands to stderr) the moment any local modification disagrees with
both the previous and incoming template version, unless the caller
listed that path in ``--accept-theirs``.

:func:`apply_writes` is the single funnel for writes: every entry from
the planner ends up here, and shell scripts under ``scripts/`` are
chmod-ed ``0o755`` so the generated repo gets executables right.

:func:`collect_orphans` walks each ``managed_scope`` (a directory that
the migration claims ownership of) and reports any file there that the
plan did NOT touch — those are typically renamed/dropped artifacts the
target should review.
"""

from __future__ import annotations

import sys

from .errors import ConflictError
from .git_ops import git_show, sha, tag_for
from .io_utils import read_bytes, write_bytes


def plan_safe_overwrites(
    template_root, target, migration, entries, accept_theirs, writes, updated, accepted
):
    for entry in entries:
        source = entry["source"]
        target_rel = entry["target"]
        condition = entry.get("enabled_when_path_exists")
        if condition and not (target / condition).exists():
            continue
        target_path = target / target_rel
        if entry.get("skip_if_target_missing") and not target_path.exists():
            continue
        base = git_show(template_root, migration["from"], source)
        theirs = git_show(template_root, migration["to"], source, required=True)
        ours = read_bytes(target_path)

        if ours == theirs:
            continue
        if base is not None and ours == base:
            writes[target_rel] = theirs
            updated.append(target_rel)
            continue
        if base is None and ours is None:
            writes[target_rel] = theirs
            updated.append(target_rel)
            continue
        if target_rel in accept_theirs:
            writes[target_rel] = theirs
            accepted.append(target_rel)
            updated.append(target_rel)
            continue

        print(f"CONFLICT: {target_rel}", file=sys.stderr)
        print(f"  base:   {sha(base)}", file=sys.stderr)
        print(f"  ours:   {sha(ours)}", file=sys.stderr)
        print(f"  theirs: {sha(theirs)}", file=sys.stderr)
        print(
            f"  inspect base:   git -C {template_root} show {tag_for(migration['from'])}:{source}",
            file=sys.stderr,
        )
        print(
            f"  inspect theirs: git -C {template_root} show {tag_for(migration['to'])}:{source}",
            file=sys.stderr,
        )
        print(f"  inspect ours:   sed -n '1,220p' {target_path}", file=sys.stderr)
        raise ConflictError(
            f"conflict detected in {target_rel}; aborted before writes"
        )


def apply_writes(target, writes):
    for rel, data in sorted(writes.items()):
        mode = None
        if rel.startswith("scripts/") and rel.endswith(".sh"):
            mode = 0o755
        write_bytes(target / rel, data, mode)


def collect_orphans(target, managed_scopes, planned_targets):
    orphans = []
    for managed_dir, first_component_prefix in sorted(managed_scopes):
        root = target / managed_dir
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(target).as_posix()
            rel_to_managed = path.relative_to(root)
            first_component = rel_to_managed.parts[0] if rel_to_managed.parts else ""
            if first_component_prefix and not first_component.startswith(
                first_component_prefix
            ):
                continue
            if rel not in planned_targets:
                orphans.append(rel)
    return sorted(orphans)
