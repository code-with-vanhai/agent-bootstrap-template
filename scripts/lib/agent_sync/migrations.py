"""Migration discovery and entry expansion (schema v1).

Encapsulates everything that turns ``core/migrations/<x>/migration.json``
into a planning input:

  - :func:`list_migrations` enumerates the available migration
    destinations on disk (used to default ``--to`` to the highest one).
  - :func:`load_migration` validates the schema, normalizes the ``from``
    field against the caller's actual current version, and rejects
    metadata mismatches.
  - :func:`list_tag_files` resolves a ``source_glob`` against a tagged
    template tree without needing a working checkout.
  - :func:`expand_file_entries` flattens ``safe_overwrite`` /
    ``adapter_files`` / ``generate_codex_command_wrappers`` into a
    uniform list of (source, target, kind) entries plus the managed
    scopes for orphan detection.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

from .errors import NoPathError, UsageError, VERSION_RE
from .git_ops import git_text, tag_for
from .io_utils import read_json, rel_path
from .versions import validate_version


def list_migrations(template_root):
    migration_root = template_root / "core" / "migrations"
    versions = []
    if not migration_root.is_dir():
        return versions
    for child in migration_root.iterdir():
        if (
            child.is_dir()
            and (child / "migration.json").is_file()
            and VERSION_RE.match(child.name)
        ):
            versions.append(child.name)
    return sorted(
        versions,
        key=lambda v: tuple(
            int(p) if p.isdigit() else 0
            for p in v.split("-", 1)[0].split(".")
        ),
    )


def load_migration(template_root, current, to_version):
    path = template_root / "core" / "migrations" / to_version / "migration.json"
    if not path.is_file():
        raise NoPathError(
            f"no migration path found for {current} -> {to_version}: missing {path}"
        )
    migration = read_json(path)
    if migration.get("schema_version") != 1:
        raise UsageError(
            f"unsupported migration schema_version: {migration.get('schema_version')}"
        )
    for key in ("version", "to"):
        validate_version(migration.get(key), f"migration {key}")

    # `from` is optional when `from_versions: []` is provided; otherwise required.
    from_versions = migration.get("from_versions")
    if from_versions is not None:
        if not isinstance(from_versions, list) or not from_versions:
            raise UsageError(
                "migration from_versions must be a non-empty array of semver strings"
            )
        for value in from_versions:
            validate_version(value, "migration from_versions[]")

    if migration.get("from") is not None:
        validate_version(migration["from"], "migration from")

    if from_versions is None and migration.get("from") is None:
        raise UsageError("migration must declare either `from` or `from_versions`")

    accepted_sources = set(from_versions or [])
    if migration.get("from") is not None:
        accepted_sources.add(migration["from"])

    if (
        current not in accepted_sources
        or migration["to"] != to_version
        or migration["version"] != to_version
    ):
        raise NoPathError(
            f"migration metadata mismatch: current={current}, requested={to_version}, "
            f"manifest from={migration.get('from')} from_versions={from_versions} "
            f"to={migration['to']} version={migration['version']}"
        )

    # Normalize: downstream code reads migration['from'] when building the sync
    # log entry and validating tag presence. Pin it to the actual source version
    # the caller is migrating from.
    migration["from"] = current
    return migration


def list_tag_files(template_root, version, pattern):
    if "**" in pattern:
        raise UsageError(f"recursive glob is not supported in schema v1: {pattern}")
    directory = str(Path(pattern).parent)
    basename_pattern = Path(pattern).name
    names = git_text(
        template_root,
        "ls-tree",
        "-r",
        "--name-only",
        tag_for(version),
        "--",
        directory,
    ).splitlines()
    matches = []
    for name in names:
        path = Path(name)
        if path.parent.as_posix() != directory:
            continue
        if fnmatch.fnmatch(path.name, basename_pattern):
            matches.append(path.as_posix())
    return sorted(matches)


def expand_file_entries(template_root, migration, include_adapters, manifest):
    entries = []
    managed_scopes = []
    adapter_report = []

    def add_entry(source_path, target_path, source_kind, item=None):
        target_path = rel_path(target_path)
        if target_path in {e["target"] for e in entries}:
            raise UsageError(
                f"multiple migration entries map to target path: {target_path}"
            )
        entry = {"source": source_path, "target": target_path, "kind": source_kind}
        if item:
            if item.get("skip_if_target_missing"):
                entry["skip_if_target_missing"] = True
            if item.get("create_if_target_missing"):
                entry["create_if_target_missing"] = True
            if item.get("enabled_when_path_exists"):
                if not isinstance(item["enabled_when_path_exists"], str):
                    raise UsageError(
                        "enabled_when_path_exists must be a relative path string"
                    )
                entry["enabled_when_path_exists"] = rel_path(
                    item["enabled_when_path_exists"]
                )
        entries.append(entry)

    for item in migration.get("safe_overwrite", []):
        if "source_glob" in item:
            target_dir = rel_path(item["target_dir"])
            managed_scopes.append((target_dir, None))
            for source_path in list_tag_files(
                template_root, migration["to"], item["source_glob"]
            ):
                add_entry(
                    source_path,
                    str(Path(target_dir) / Path(source_path).name),
                    "safe_overwrite",
                    item,
                )
        else:
            add_entry(
                rel_path(item["source"]),
                rel_path(item["target"]),
                "safe_overwrite",
                item,
            )

    adapter_files = migration.get("adapter_files", [])
    if adapter_files and include_adapters:
        for item in adapter_files:
            add_entry(
                rel_path(item["source"]),
                rel_path(item["target"]),
                "adapter_files",
                item,
            )
    elif adapter_files:
        for item in adapter_files:
            adapter_report.append(rel_path(item["target"]))

    generator = migration.get("generate_codex_command_wrappers") or {}
    if generator:
        feature = generator.get("enabled_when_feature_present")
        features = manifest.get("features_enabled") or []
        if feature in features:
            managed_scopes.append((rel_path(generator["target_dir"]), "agent-"))

    return entries, managed_scopes, adapter_report
