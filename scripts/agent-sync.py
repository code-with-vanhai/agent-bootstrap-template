#!/usr/bin/env python3
import argparse
import datetime as dt
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import OrderedDict, deque
from pathlib import Path


EXIT_USAGE = 2
EXIT_DIRTY = 10
EXIT_CONFLICT = 20
EXIT_VALIDATION = 30
EXIT_NO_PATH = 40
EXIT_LOCKED = 50

VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$")


class SyncError(Exception):
    exit_code = 1


class UsageError(SyncError):
    exit_code = EXIT_USAGE


class DirtyError(SyncError):
    exit_code = EXIT_DIRTY


class ConflictError(SyncError):
    exit_code = EXIT_CONFLICT


class NoPathError(SyncError):
    exit_code = EXIT_NO_PATH


class LockError(SyncError):
    exit_code = EXIT_LOCKED


def run_git(repo, *args, check=True, text=False):
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=text,
    )
    if check and result.returncode != 0:
        stderr = result.stderr.strip() if text else result.stderr.decode("utf-8", "replace").strip()
        raise SyncError(f"git {' '.join(args)} failed: {stderr}")
    return result


def git_text(repo, *args):
    return run_git(repo, *args, text=True).stdout


def git_bytes(repo, *args, check=True):
    return run_git(repo, *args, check=check, text=False)


def die(message, code=1):
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def validate_version(value, label):
    if not value or not VERSION_RE.match(value):
        raise UsageError(f"{label} must be semver without v prefix: {value!r}")


def tag_for(version):
    return f"v{version}"


def tag_exists(repo, version):
    tag = tag_for(version)
    result = run_git(repo, "rev-parse", "--verify", "--quiet", f"{tag}^{{commit}}", check=False)
    return result.returncode == 0


def tag_commit(repo, version):
    tag = tag_for(version)
    return git_text(repo, "rev-parse", f"{tag}^{{commit}}").strip()


def git_show(repo, version, source_path, required=False):
    tag = tag_for(version)
    result = git_bytes(repo, "show", f"{tag}:{source_path}", check=False)
    if result.returncode == 0:
        return result.stdout
    if required:
        stderr = result.stderr.decode("utf-8", "replace").strip()
        raise UsageError(f"migration references missing source at {tag}:{source_path}: {stderr}")
    return None


def sha(data):
    if data is None:
        return "missing"
    return hashlib.sha256(data).hexdigest()


def rel_path(path):
    normalized = Path(path)
    if normalized.is_absolute() or ".." in normalized.parts:
        raise UsageError(f"path must be relative and stay inside target: {path}")
    return normalized.as_posix()


def read_bytes(path):
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def write_bytes(path, data, mode=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if mode is not None:
        path.chmod(mode)


def read_json(path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh, object_pairs_hook=OrderedDict)


def dump_manifest(data):
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def list_migrations(template_root):
    migration_root = template_root / "core" / "migrations"
    versions = []
    if not migration_root.is_dir():
        return versions
    for child in migration_root.iterdir():
        if child.is_dir() and (child / "migration.json").is_file() and VERSION_RE.match(child.name):
            versions.append(child.name)
    return sorted(versions, key=lambda v: tuple(int(p) if p.isdigit() else 0 for p in v.split("-", 1)[0].split(".")))


def load_migration(template_root, current, to_version):
    path = template_root / "core" / "migrations" / to_version / "migration.json"
    if not path.is_file():
        raise NoPathError(f"no migration path found for {current} -> {to_version}: missing {path}")
    migration = read_json(path)
    if migration.get("schema_version") != 1:
        raise UsageError(f"unsupported migration schema_version: {migration.get('schema_version')}")
    for key in ("version", "to"):
        validate_version(migration.get(key), f"migration {key}")

    # `from` is optional when `from_versions: []` is provided; otherwise required.
    from_versions = migration.get("from_versions")
    if from_versions is not None:
        if not isinstance(from_versions, list) or not from_versions:
            raise UsageError("migration from_versions must be a non-empty array of semver strings")
        for value in from_versions:
            validate_version(value, "migration from_versions[]")

    if migration.get("from") is not None:
        validate_version(migration["from"], "migration from")

    if from_versions is None and migration.get("from") is None:
        raise UsageError("migration must declare either `from` or `from_versions`")

    accepted_sources = set(from_versions or [])
    if migration.get("from") is not None:
        accepted_sources.add(migration["from"])

    if current not in accepted_sources or migration["to"] != to_version or migration["version"] != to_version:
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


def target_clean(target):
    status = git_text(target, "status", "--porcelain")
    return status == ""


def detect_current_version(manifest):
    for key in ("synced_to_template_version", "instantiated_from_template_version"):
        value = manifest.get(key)
        if value:
            return value
    raise UsageError("cannot detect current template version")


def acquire_lock(target, from_version, to_version):
    lock = target / ".agent" / ".sync.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    body = (
        f"pid={os.getpid()}\n"
        f"created_at={dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        f"from={from_version}\n"
        f"to={to_version}\n"
    ).encode("utf-8")
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        try:
            contents = lock.read_text(encoding="utf-8")
        except OSError:
            contents = "<cannot read lock>"
        raise LockError(f"sync lock already exists at {lock}\n{contents}")
    with os.fdopen(fd, "wb") as fh:
        fh.write(body)
    return lock


def list_tag_files(template_root, version, pattern):
    if "**" in pattern:
        raise UsageError(f"recursive glob is not supported in schema v1: {pattern}")
    directory = str(Path(pattern).parent)
    basename_pattern = Path(pattern).name
    names = git_text(template_root, "ls-tree", "-r", "--name-only", tag_for(version), "--", directory).splitlines()
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
            raise UsageError(f"multiple migration entries map to target path: {target_path}")
        entry = {"source": source_path, "target": target_path, "kind": source_kind}
        if item:
            if item.get("skip_if_target_missing"):
                entry["skip_if_target_missing"] = True
            if item.get("enabled_when_path_exists"):
                if not isinstance(item["enabled_when_path_exists"], str):
                    raise UsageError("enabled_when_path_exists must be a relative path string")
                entry["enabled_when_path_exists"] = rel_path(item["enabled_when_path_exists"])
        entries.append(entry)

    for item in migration.get("safe_overwrite", []):
        if "source_glob" in item:
            target_dir = rel_path(item["target_dir"])
            managed_scopes.append((target_dir, None))
            for source_path in list_tag_files(template_root, migration["to"], item["source_glob"]):
                add_entry(source_path, str(Path(target_dir) / Path(source_path).name), "safe_overwrite", item)
        else:
            add_entry(rel_path(item["source"]), rel_path(item["target"]), "safe_overwrite", item)

    adapter_files = migration.get("adapter_files", [])
    if adapter_files and include_adapters:
        for item in adapter_files:
            add_entry(rel_path(item["source"]), rel_path(item["target"]), "adapter_files", item)
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


def plan_safe_overwrites(template_root, target, migration, entries, accept_theirs, writes, updated, accepted):
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
        print(f"  inspect base:   git -C {template_root} show {tag_for(migration['from'])}:{source}", file=sys.stderr)
        print(f"  inspect theirs: git -C {template_root} show {tag_for(migration['to'])}:{source}", file=sys.stderr)
        print(f"  inspect ours:   sed -n '1,220p' {target_path}", file=sys.stderr)
        raise ConflictError(f"conflict detected in {target_rel}; aborted before writes")


def plan_patches(target, migration, writes, updated):
    for patch in migration.get("patches", []):
        target_rel = rel_path(patch["file"])
        current = writes.get(target_rel)
        if current is None:
            current = read_bytes(target / target_rel)
        if current is None:
            raise ConflictError(f"patch target is missing: {target_rel}")
        text = current.decode("utf-8")

        skip = patch.get("skip_if_contains")
        if skip and skip in text:
            continue

        anchor = patch["anchor"]
        matches = [match.start() for match in re.finditer(re.escape(anchor), text)]
        if len(matches) != 1:
            raise ConflictError(f"patch anchor for {target_rel} matched {len(matches)} times; expected exactly 1")

        line_end = text.find("\n", matches[0])
        if line_end == -1:
            line_end = len(text)
            insert_at = line_end
            separator = "\n"
        else:
            insert_at = line_end + 1
            separator = ""
        patched = text[:insert_at] + separator + patch["insert_after_first_match"] + text[insert_at:]

        if patch.get("require_bash_syntax_ok_after"):
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as fh:
                fh.write(patched)
                temp_name = fh.name
            try:
                result = subprocess.run(["bash", "-n", temp_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if result.returncode != 0:
                    raise ConflictError(f"patched {target_rel} failed bash -n: {result.stderr.strip()}")
            finally:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass

        writes[target_rel] = patched.encode("utf-8")
        updated.append(f"{target_rel} patched")


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


def plan_codex_wrappers(template_root, target, migration, manifest, accept_theirs, writes, updated, accepted):
    generator = migration.get("generate_codex_command_wrappers") or {}
    if not generator:
        return
    feature = generator.get("enabled_when_feature_present")
    features = manifest.get("features_enabled") or []
    if feature not in features:
        return

    target_dir = rel_path(generator["target_dir"])
    for source_path in list_tag_files(template_root, migration["to"], generator["commands_source_glob"]):
        command_name = Path(source_path).stem
        target_rel = (Path(target_dir) / f"agent-{command_name}" / "SKILL.md").as_posix()
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
        raise ConflictError(f"generated Codex wrapper already exists with different content: {target_rel}")


def ordered_manifest_with_sync(data, sync_values):
    result = OrderedDict()
    inserted = False
    for key, value in data.items():
        if key in sync_values:
            continue
        result[key] = value
        if key == "instantiated_from_template_version":
            for sync_key in ("synced_to_template_version", "synced_to_template_commit", "synced_at"):
                if sync_key in sync_values:
                    result[sync_key] = sync_values[sync_key]
            inserted = True
    if not inserted:
        for sync_key in ("synced_to_template_version", "synced_to_template_commit", "synced_at"):
            if sync_key in sync_values:
                result[sync_key] = sync_values[sync_key]
    return result


def plan_manifest(template_root, target, migration, manifest, sync_now, writes, updated):
    updates = migration.get("manifest_updates") or {}
    new_manifest = OrderedDict(manifest)

    replace = updates.get("replace") or {}
    for key, value in replace.items():
        if key not in ("synced_to_template_version", "synced_to_template_commit", "synced_at"):
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

    new_manifest = ordered_manifest_with_sync(new_manifest, sync_values)
    manifest_bytes = dump_manifest(new_manifest)
    target_rel = ".agent/manifest.json"
    if read_bytes(target / target_rel) != manifest_bytes:
        writes[target_rel] = manifest_bytes
        updated.append(target_rel)


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
            if first_component_prefix and not first_component.startswith(first_component_prefix):
                continue
            if rel not in planned_targets:
                orphans.append(rel)
    return sorted(orphans)


def sync_log_entry(sync_now, migration, template_commit, updated, accepted, orphans, validation):
    lines = [
        f"## {sync_now} - Sync to {migration['to']}",
        "",
        f"- From: {migration['from']}",
        f"- To: {migration['to']}",
        f"- Template commit: {template_commit[:7]}",
        "- Updated:",
    ]
    if updated:
        lines.extend(f"  - {item}" for item in updated)
    else:
        lines.append("  - none")
    lines.append("- Accepted theirs:")
    if accepted:
        lines.extend(f"  - {item}" for item in accepted)
    else:
        lines.append("  - none")
    lines.extend([
        "- Preserved:",
        "  - .agent/project-profile.md",
        "  - .agent/gates.md",
        "  - .agent/ownership.md",
        "  - scripts/agent-eval.sh repo-specific gates",
        "- Warnings:",
    ])
    if orphans:
        lines.extend(f"  - orphan managed file: {item}" for item in orphans)
    else:
        lines.append("  - no managed-directory orphan files")
    lines.append("- Validation:")
    for item in validation:
        lines.append(f"  - {item}")
    return "\n".join(lines) + "\n"


def append_sync_log(target, entry):
    path = target / ".agent" / "sync-log.md"
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if not existing.endswith("\n"):
            existing += "\n"
        text = existing + "\n" + entry
    else:
        text = "# Sync Log\n\n" + entry
    path.write_text(text, encoding="utf-8")


def apply_writes(target, writes):
    for rel, data in sorted(writes.items()):
        mode = None
        if rel.startswith("scripts/") and rel.endswith(".sh"):
            mode = 0o755
        write_bytes(target / rel, data, mode)


# ---------------------------------------------------------------------------
# Multi-hop migration walker (P1-2)
#
# These helpers add safe chain orchestration without rewriting the single-hop
# engine. When --multi-hop is absent, main() takes its existing single-hop
# code path verbatim.
# ---------------------------------------------------------------------------


def _semver_tuple(version):
    return tuple(int(p) if p.isdigit() else 0 for p in version.split("-", 1)[0].split("."))


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
            if not (child.is_dir() and (child / "migration.json").is_file() and VERSION_RE.match(child.name)):
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


def _execute_hop_on_temp(template_root, work_target, accept_theirs, args, hop_source, hop_to, sync_now, dry_run_print):
    """Plan and apply one hop's writes against a writable rehearsal directory.

    `work_target` is an ephemeral copy of the real target. Always advances the
    rehearsal tree by writing the planned changes through `apply_writes` so the
    next hop sees the right state. Never validates and never appends to the
    rehearsal sync-log.
    """

    manifest_path = work_target / ".agent" / "manifest.json"
    manifest = read_json(manifest_path)
    migration = load_migration(template_root, hop_source, hop_to)

    writes = {}
    updated = []
    accepted = []
    entries, managed_scopes, adapter_report = expand_file_entries(
        template_root, migration, args.with_adapters, manifest
    )
    plan_safe_overwrites(template_root, work_target, migration, entries, accept_theirs, writes, updated, accepted)
    plan_patches(work_target, migration, writes, updated)
    plan_codex_wrappers(template_root, work_target, migration, manifest, accept_theirs, writes, updated, accepted)
    plan_manifest(template_root, work_target, migration, manifest, sync_now, writes, updated)

    planned_targets = set(writes) | {entry["target"] for entry in entries}
    generator = migration.get("generate_codex_command_wrappers") or {}
    if generator and generator.get("enabled_when_feature_present") in (manifest.get("features_enabled") or []):
        for source_path in list_tag_files(template_root, migration["to"], generator["commands_source_glob"]):
            command_name = Path(source_path).stem
            planned_targets.add(
                (Path(generator["target_dir"]) / f"agent-{command_name}" / "SKILL.md").as_posix()
            )
    orphans = collect_orphans(work_target, managed_scopes, planned_targets)

    if dry_run_print:
        print(f"  hop {hop_source} -> {hop_to}: {len(writes)} change(s)")
        for path in sorted(writes):
            print(f"    update {path}")
        for path in adapter_report:
            print(f"    adapter report-only {path} (pass --with-adapters to include)")
        for path in orphans:
            print(f"    warning orphan managed file: {path}")

    apply_writes(work_target, writes)

    return {
        "from": hop_source,
        "to": hop_to,
        "writes": dict(writes),
        "updated": list(updated),
        "accepted": list(accepted),
        "adapter_report": list(adapter_report),
        "orphans": list(orphans),
    }


def multi_hop_sync_log_entry(sync_now, original_from, final_to, chain, template_commit, updated, accepted, orphans, validation):
    chain_display = " -> ".join([original_from] + list(chain))
    lines = [
        f"## {sync_now} - Sync to {final_to} (multi-hop from {original_from})",
        "",
        f"- From: {original_from}",
        f"- To: {final_to}",
        f"- Chain: {chain_display}",
        f"- Template commit: {template_commit[:7]}",
        "- Updated:",
    ]
    if updated:
        lines.extend(f"  - {item}" for item in updated)
    else:
        lines.append("  - none")
    lines.append("- Accepted theirs:")
    if accepted:
        lines.extend(f"  - {item}" for item in accepted)
    else:
        lines.append("  - none")
    lines.extend([
        "- Preserved:",
        "  - .agent/project-profile.md",
        "  - .agent/gates.md",
        "  - .agent/ownership.md",
        "  - scripts/agent-eval.sh repo-specific gates",
        "- Warnings:",
    ])
    if orphans:
        lines.extend(f"  - orphan managed file: {item}" for item in orphans)
    else:
        lines.append("  - no managed-directory orphan files")
    lines.append("- Validation:")
    for item in validation:
        lines.append(f"  - {item}")
    return "\n".join(lines) + "\n"


def _run_multi_hop(args, template_root, target, accept_theirs):
    """Orchestrate a multi-hop migration chain.

    Sign-off invariants:
    1. Preflight (target existence/git/dirty/current-version) runs before any
       temp materialization, for both dry-run and apply.
    2. Single-hop semantics are not affected; main() only dispatches here when
       --multi-hop is set.
    3. On --apply, exactly one aggregated sync-log entry is appended after the
       full target batch is applied successfully.
    """

    if not target.exists():
        raise UsageError(f"target does not exist: {target}")
    if run_git(target, "rev-parse", "--git-dir", check=False).returncode != 0:
        raise UsageError(f"target is not a git repo: {target}")
    if not args.allow_dirty and not target_clean(target):
        raise DirtyError(
            f"target worktree is dirty: {target}. Commit/stash changes or pass --allow-dirty."
        )
    manifest_path = target / ".agent" / "manifest.json"
    if not manifest_path.is_file():
        raise UsageError(f"target is missing .agent/manifest.json: {target}")
    manifest = read_json(manifest_path)
    current = detect_current_version(manifest)
    validate_version(current, "current template version")

    if args.to is None:
        raise UsageError("--multi-hop requires --to <version>")
    validate_version(args.to, "--to")
    to_version = args.to

    if current == to_version:
        print(f"Target already synced to {to_version}; no-op.")
        return 0

    chain = compute_migration_chain(template_root, current, to_version)
    if not chain:
        raise NoPathError(f"empty migration chain from {current} to {to_version}")

    for version in [current] + chain:
        if not tag_exists(template_root, version):
            raise UsageError(
                f"version {version} requires tag {tag_for(version)}; try git fetch --tags"
            )

    sync_now = os.environ.get("AGENT_SYNC_NOW") or dt.datetime.now(dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    print(f"Multi-hop {'apply' if args.apply else 'dry run'}: {current} -> {to_version}")
    print(f"Chain: {' -> '.join([current] + chain)}")

    temp_parent = Path(tempfile.mkdtemp(prefix="agent-sync-chain-"))
    lock_path = None
    try:
        temp_target = temp_parent / "target"
        shutil.copytree(
            target,
            temp_target,
            symlinks=True,
            ignore=shutil.ignore_patterns(".git"),
        )
        temp_lock = temp_target / ".agent" / ".sync.lock"
        if temp_lock.exists():
            temp_lock.unlink()

        hop_results = []
        hop_source = current
        for hop_to in chain:
            print(f"Hop {hop_source} -> {hop_to}")
            result = _execute_hop_on_temp(
                template_root,
                temp_target,
                accept_theirs,
                args,
                hop_source,
                hop_to,
                sync_now,
                dry_run_print=not args.apply,
            )
            hop_results.append(result)
            hop_source = hop_to

        if not args.apply:
            return 0

        # Re-check target_clean AFTER rehearsal but BEFORE acquire_lock, because
        # acquire_lock writes .agent/.sync.lock into the target tree itself
        # (which would otherwise make this very check fail).
        if not args.allow_dirty and not target_clean(target):
            raise DirtyError(
                f"target worktree became dirty during rehearsal: {target}. Aborting before write."
            )
        lock_path = acquire_lock(target, current, to_version)

        touched = set()
        for r in hop_results:
            touched.update(r["writes"].keys())
        final_writes = {}
        for rel in sorted(touched):
            final_writes[rel] = (temp_target / rel).read_bytes()
        apply_writes(target, final_writes)

        try:
            validation = run_validation(target, args.verify_fast)
        except SystemExit as exc:
            if exc.code == EXIT_VALIDATION:
                print("Migration applied but validation failed. To revert:", file=sys.stderr)
                print(f"  git -C {target} restore .", file=sys.stderr)
                print(f"  git -C {target} clean -fd", file=sys.stderr)
            raise

        merged_updated, merged_accepted, merged_orphans = [], [], []
        seen_updated, seen_accepted, seen_orphans = set(), set(), set()
        for r in hop_results:
            for u in r["updated"]:
                if u not in seen_updated:
                    merged_updated.append(u)
                    seen_updated.add(u)
            for a in r["accepted"]:
                if a not in seen_accepted:
                    merged_accepted.append(a)
                    seen_accepted.add(a)
            for o in r["orphans"]:
                if o not in seen_orphans:
                    merged_orphans.append(o)
                    seen_orphans.add(o)

        final_template_commit = tag_commit(template_root, to_version)
        entry = multi_hop_sync_log_entry(
            sync_now,
            current,
            to_version,
            chain,
            final_template_commit,
            merged_updated,
            merged_accepted,
            merged_orphans,
            validation,
        )
        append_sync_log(target, entry)

        print(f"Synced {target} from {current} to {to_version} via {' -> '.join([current] + chain)}.")
        return 0
    finally:
        if lock_path is not None:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
        shutil.rmtree(temp_parent, ignore_errors=True)


def run_validation(target, verify_fast):
    validation = []
    validator = target / "scripts" / "agent-validate.sh"
    if validator.is_file():
        result = subprocess.run(
            ["bash", str(validator)],
            cwd=str(target),
            env={**os.environ, "AGENT_ROOT": str(target)},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            print(result.stdout, end="")
            print(result.stderr, end="", file=sys.stderr)
            raise SystemExit(EXIT_VALIDATION)
        validation.append("agent-validate: passed")

    agent_eval = target / "scripts" / "agent-eval.sh"
    if agent_eval.is_file():
        result = subprocess.run(["bash", "-n", str(agent_eval)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            print(result.stderr, end="", file=sys.stderr)
            raise SystemExit(EXIT_VALIDATION)
        validation.append("bash -n agent-eval.sh: passed")

    if verify_fast:
        result = subprocess.run(["bash", str(agent_eval), "fast"], cwd=str(target), text=True)
        if result.returncode != 0:
            raise SystemExit(EXIT_VALIDATION)
        validation.append("agent-eval fast: passed")
    return validation


def main(argv):
    parser = argparse.ArgumentParser(description="Sync an Agent Bootstrap Kit target repository to a template version.")
    parser.add_argument("--target", required=True)
    parser.add_argument("--to")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--template-root", required=True)
    parser.add_argument("--verify-fast", action="store_true")
    parser.add_argument("--with-adapters", action="store_true")
    parser.add_argument("--accept-theirs", action="append", default=[])
    parser.add_argument(
        "--multi-hop",
        action="store_true",
        help="Walk a deterministic chain of single-hop migrations from the target's current version up to --to. Dry-run by default; --apply rehearses on a temp clone before touching the target.",
    )
    args = parser.parse_args(argv)

    template_root = Path(args.template_root).resolve()
    target = Path(args.target).resolve()
    accept_theirs = {rel_path(path) for path in args.accept_theirs}

    if not (template_root / ".git").exists():
        raise UsageError(f"template root is not a git repo: {template_root}")
    if sys.version_info < (3, 8):
        raise UsageError("python3 >= 3.8 is required")

    if args.multi_hop:
        return _run_multi_hop(args, template_root, target, accept_theirs)

    if args.to is not None:
        validate_version(args.to, "--to")
    migrations = list_migrations(template_root)
    to_version = args.to or (migrations[-1] if migrations else None)
    validate_version(to_version, "--to")

    migration_path = template_root / "core" / "migrations" / to_version / "migration.json"
    if not migration_path.is_file():
        raise NoPathError(f"no migration path found for requested target version {to_version}: missing {migration_path}")
    migration = read_json(migration_path)
    if migration.get("schema_version") != 1:
        raise UsageError(f"unsupported migration schema_version: {migration.get('schema_version')}")
    for key in ("version", "to"):
        validate_version(migration.get(key), f"migration {key}")

    candidate_sources = []
    if migration.get("from") is not None:
        validate_version(migration["from"], "migration from")
        candidate_sources.append(migration["from"])
    from_versions_pre = migration.get("from_versions")
    if isinstance(from_versions_pre, list):
        for value in from_versions_pre:
            validate_version(value, "migration from_versions[]")
            candidate_sources.append(value)
    if not candidate_sources:
        raise UsageError("migration must declare either `from` or `from_versions`")

    if not tag_exists(template_root, migration["to"]):
        raise UsageError(f"version {migration['to']} requires tag {tag_for(migration['to'])}; try git fetch --tags")
    for version in candidate_sources:
        if not tag_exists(template_root, version):
            raise UsageError(f"version {version} requires tag {tag_for(version)}; try git fetch --tags")

    if not target.exists():
        raise UsageError(f"target does not exist: {target}")
    if run_git(target, "rev-parse", "--git-dir", check=False).returncode != 0:
        raise UsageError(f"target is not a git repo: {target}")
    if not args.allow_dirty and not target_clean(target):
        raise DirtyError(f"target worktree is dirty: {target}. Commit/stash changes or pass --allow-dirty.")

    manifest_path = target / ".agent" / "manifest.json"
    if not manifest_path.is_file():
        raise UsageError(f"target is missing .agent/manifest.json: {target}")
    manifest = read_json(manifest_path)
    current = detect_current_version(manifest)
    validate_version(current, "current template version")

    if current == to_version:
        print(f"Target already synced to {to_version}; no-op.")
        return 0

    migration = load_migration(template_root, current, to_version)

    lock_path = None
    if args.apply:
        lock_path = acquire_lock(target, current, to_version)

    try:
        writes = {}
        updated = []
        accepted = []
        entries, managed_scopes, adapter_report = expand_file_entries(template_root, migration, args.with_adapters, manifest)

        plan_safe_overwrites(template_root, target, migration, entries, accept_theirs, writes, updated, accepted)
        plan_patches(target, migration, writes, updated)
        plan_codex_wrappers(template_root, target, migration, manifest, accept_theirs, writes, updated, accepted)

        sync_now = os.environ.get("AGENT_SYNC_NOW") or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        plan_manifest(template_root, target, migration, manifest, sync_now, writes, updated)

        planned_targets = set(writes) | {entry["target"] for entry in entries}
        generator = migration.get("generate_codex_command_wrappers") or {}
        if generator and generator.get("enabled_when_feature_present") in (manifest.get("features_enabled") or []):
            for source_path in list_tag_files(template_root, migration["to"], generator["commands_source_glob"]):
                command_name = Path(source_path).stem
                planned_targets.add((Path(generator["target_dir"]) / f"agent-{command_name}" / "SKILL.md").as_posix())
        orphans = collect_orphans(target, managed_scopes, planned_targets)

        if not args.apply:
            print(f"Dry run: {current} -> {to_version}")
            for path in sorted(writes):
                print(f"  update {path}")
            for path in adapter_report:
                print(f"  adapter report-only {path} (pass --with-adapters to include)")
            for path in orphans:
                print(f"  warning orphan managed file: {path}")
            return 0

        apply_writes(target, writes)
        validation = run_validation(target, args.verify_fast)
        entry = sync_log_entry(sync_now, migration, tag_commit(template_root, migration["to"]), updated, accepted, orphans, validation)
        append_sync_log(target, entry)
        print(f"Synced {target} from {current} to {to_version}.")
        return 0
    except SystemExit as exc:
        if exc.code == EXIT_VALIDATION:
            print("Migration applied but validation failed. To revert:", file=sys.stderr)
            print(f"  git -C {target} restore .", file=sys.stderr)
            print(f"  git -C {target} clean -fd", file=sys.stderr)
        raise
    finally:
        if lock_path is not None:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except SyncError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(exc.exit_code)
