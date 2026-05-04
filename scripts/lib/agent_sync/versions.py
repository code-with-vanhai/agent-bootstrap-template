"""Semver validation, current-version detection, and migration-chain BFS.

Three concerns folded into one module because they all reduce to "what
version are we at" and "how do we get from version A to version B":

  - :func:`validate_version` rejects anything that does not match the
    project semver shape (no ``v`` prefix; pre-release allowed),
  - :func:`detect_current_version` reads the manifest to find the
    target's current sync state, and
  - :func:`compute_migration_chain` does a deterministic BFS over the
    template's ``core/migrations/<x>/migration.json`` adjacency map to
    produce the shortest hop sequence from ``current`` to ``to_version``.
"""

from __future__ import annotations

from collections import deque

from .errors import NoPathError, UsageError, VERSION_RE
from .io_utils import read_json


def validate_version(value, label):
    if not value or not VERSION_RE.match(value):
        raise UsageError(f"{label} must be semver without v prefix: {value!r}")


def _semver_tuple(version):
    return tuple(
        int(p) if p.isdigit() else 0
        for p in version.split("-", 1)[0].split(".")
    )


def detect_current_version(manifest):
    for key in ("synced_to_template_version", "instantiated_from_template_version"):
        value = manifest.get(key)
        if value:
            return value
    raise UsageError("cannot detect current template version")


def compute_migration_chain(template_root, current, to_version):
    """Compute a deterministic shortest BFS chain of destination versions.

    Returns an ordered list starting at the first hop's `to` and ending at
    `to_version`. Returns an empty list when current == to_version. Raises
    NoPathError when no chain exists. Tie-break on equal BFS depth prefers
    the next hop with the lowest semver tuple.
    """

    if current == to_version:
        return []

    migration_root = template_root / "core" / "migrations"
    adjacency = {}  # src_version -> list[dst_version]
    if migration_root.is_dir():
        for child in migration_root.iterdir():
            if not (
                child.is_dir()
                and (child / "migration.json").is_file()
                and VERSION_RE.match(child.name)
            ):
                continue
            try:
                data = read_json(child / "migration.json")
            except Exception:
                continue
            if data.get("schema_version") != 1:
                continue
            dst = data.get("to")
            if not isinstance(dst, str) or not VERSION_RE.match(dst):
                continue
            sources = set()
            from_versions = data.get("from_versions")
            if isinstance(from_versions, list):
                for v in from_versions:
                    if isinstance(v, str) and VERSION_RE.match(v):
                        sources.add(v)
            from_value = data.get("from")
            if isinstance(from_value, str) and VERSION_RE.match(from_value):
                sources.add(from_value)
            for src in sources:
                adjacency.setdefault(src, []).append(dst)

    for src, dsts in adjacency.items():
        adjacency[src] = sorted(set(dsts), key=_semver_tuple)

    queue = deque()
    queue.append((current, [current]))
    visited = {current}
    while queue:
        node, path = queue.popleft()
        if node == to_version:
            return path[1:]
        for nxt in adjacency.get(node, []):
            if nxt in visited:
                continue
            visited.add(nxt)
            queue.append((nxt, path + [nxt]))

    neighbors = adjacency.get(current) or []
    raise NoPathError(
        f"no migration chain from {current} to {to_version}; "
        f"reachable next hops from {current}: {neighbors or 'none'}"
    )
