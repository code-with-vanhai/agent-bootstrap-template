#!/usr/bin/env python3
import argparse
import datetime as dt
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import OrderedDict
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
    for key in ("version", "from", "to"):
        validate_version(migration.get(key), f"migration {key}")
    if migration["from"] != current or migration["to"] != to_version or migration["version"] != to_version:
        raise NoPathError(
            f"migration metadata mismatch: current={current}, requested={to_version}, "
            f"manifest from={migration['from']} to={migration['to']} version={migration['version']}"
        )
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

    def add_entry(source_path, target_path, source_kind):
        target_path = rel_path(target_path)
        if target_path in {e["target"] for e in entries}:
            raise UsageError(f"multiple migration entries map to target path: {target_path}")
        entries.append({"source": source_path, "target": target_path, "kind": source_kind})

    for item in migration.get("safe_overwrite", []):
        if "source_glob" in item:
            target_dir = rel_path(item["target_dir"])
            managed_scopes.append((target_dir, None))
            for source_path in list_tag_files(template_root, migration["to"], item["source_glob"]):
                add_entry(source_path, str(Path(target_dir) / Path(source_path).name), "safe_overwrite")
        else:
            add_entry(rel_path(item["source"]), rel_path(item["target"]), "safe_overwrite")

    adapter_files = migration.get("adapter_files", [])
    if adapter_files and include_adapters:
        for item in adapter_files:
            add_entry(rel_path(item["source"]), rel_path(item["target"]), "adapter_files")
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
        base = git_show(template_root, migration["from"], source)
        theirs = git_show(template_root, migration["to"], source, required=True)
        target_path = target / target_rel
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
    args = parser.parse_args(argv)

    template_root = Path(args.template_root).resolve()
    target = Path(args.target).resolve()
    accept_theirs = {rel_path(path) for path in args.accept_theirs}

    if not (template_root / ".git").exists():
        raise UsageError(f"template root is not a git repo: {template_root}")
    if sys.version_info < (3, 8):
        raise UsageError("python3 >= 3.8 is required")

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
    for key in ("version", "from", "to"):
        validate_version(migration.get(key), f"migration {key}")

    for version in (migration["from"], migration["to"]):
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
