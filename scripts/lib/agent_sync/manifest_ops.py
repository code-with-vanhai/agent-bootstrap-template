"""``.agent/manifest.json`` ordering and update planning.

The manifest's three sync fields (``synced_to_template_version``,
``synced_to_template_commit``, ``synced_at``) must always sit
immediately after ``instantiated_from_template_version`` so that diffing
two manifests at different sync states stays readable.
:func:`ordered_manifest_with_sync` enforces that placement.

:func:`plan_manifest` consumes the migration's ``manifest_updates``
block (replace / replace_from_git_tag / append_to_array_unique /
merge_array_unique) and queues a single write into the planner's
``writes`` dict if the resulting JSON differs from what is on disk.
"""

from __future__ import annotations

from collections import OrderedDict

from .git_ops import tag_commit
from .io_utils import dump_manifest, read_bytes
from .tracked_files import populate_tracked_files
from .versions import validate_version


def ordered_manifest_with_sync(data, sync_values):
    result = OrderedDict()
    inserted = False
    for key, value in data.items():
        if key in sync_values:
            continue
        result[key] = value
        if key == "instantiated_from_template_version":
            for sync_key in (
                "synced_to_template_version",
                "synced_to_template_commit",
                "synced_at",
            ):
                if sync_key in sync_values:
                    result[sync_key] = sync_values[sync_key]
            inserted = True
    if not inserted:
        for sync_key in (
            "synced_to_template_version",
            "synced_to_template_commit",
            "synced_at",
        ):
            if sync_key in sync_values:
                result[sync_key] = sync_values[sync_key]
    return result


def plan_manifest(template_root, target, migration, manifest, sync_now, writes, updated):
    updates = migration.get("manifest_updates") or {}
    new_manifest = OrderedDict(manifest)

    replace = updates.get("replace") or {}
    for key, value in replace.items():
        if key not in (
            "synced_to_template_version",
            "synced_to_template_commit",
            "synced_at",
        ):
            new_manifest[key] = value

    sync_values = OrderedDict()
    if "synced_to_template_version" in replace:
        sync_values["synced_to_template_version"] = replace["synced_to_template_version"]

    for key, version in (updates.get("replace_from_git_tag") or {}).items():
        validate_version(version, f"replace_from_git_tag {key}")
        if key == "synced_to_template_commit":
            sync_values[key] = tag_commit(template_root, version)
        else:
            new_manifest[key] = tag_commit(template_root, version)

    sync_values["synced_at"] = sync_now

    for key, value in (updates.get("append_to_array_unique") or {}).items():
        existing = new_manifest.get(key)
        if not isinstance(existing, list):
            existing = []
        if not any(isinstance(item, str) and value in item for item in existing):
            existing.append(value)
        new_manifest[key] = existing

    for key, values in (updates.get("merge_array_unique") or {}).items():
        existing = new_manifest.get(key)
        if not isinstance(existing, list):
            existing = []
        for value in values:
            if value not in existing:
                existing.append(value)
        new_manifest[key] = existing

    # Stage 3.1 opt-in: when the migration sets
    # ``manifest_updates.update_tracked_files: true``, fold the hop's
    # planned writes into ``manifest.tracked_files`` so a future
    # fast-path / backfill release can reason about per-file baseline
    # checksums. Default behavior is a no-op so legacy migrations and
    # fixtures (e.g. tests/migrations/0.3.0 diff -r assertion) stay
    # byte-identical post-apply.
    new_manifest = populate_tracked_files(new_manifest, migration, writes)

    new_manifest = ordered_manifest_with_sync(new_manifest, sync_values)
    manifest_bytes = dump_manifest(new_manifest)
    target_rel = ".agent/manifest.json"
    if read_bytes(target / target_rel) != manifest_bytes:
        writes[target_rel] = manifest_bytes
        updated.append(target_rel)
