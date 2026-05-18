#!/usr/bin/env python3
"""Advisory path locks for agents sharing one working tree."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


TTL_MINUTES_LIMIT = 60
LOCK_SCHEMA_VERSION = 1


class LockConflictError(RuntimeError):
    """Raised when a requested path overlaps an active lock."""

    def __init__(self, lock: dict[str, Any]) -> None:
        self.lock = lock
        super().__init__(
            "lock conflict with session "
            f"{lock.get('session_id', '<unknown>')} ({lock.get('task', '<unknown>')})"
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def _normalize_path_pattern(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.strip("/")


def _split_paths(paths: str | Iterable[str]) -> list[str]:
    if isinstance(paths, str):
        raw = paths.split(",")
    else:
        raw = list(paths)
    normalized = [_normalize_path_pattern(item) for item in raw]
    return [item for item in normalized if item]


def _prefix_before_glob(pattern: str) -> str:
    indexes = [index for index in (pattern.find("*"), pattern.find("?")) if index >= 0]
    if not indexes:
        return pattern
    return pattern[: min(indexes)].rstrip("/")


def _paths_overlap(paths_a: Iterable[str], paths_b: Iterable[str]) -> bool:
    normalized_a = [_normalize_path_pattern(path) for path in paths_a]
    normalized_b = [_normalize_path_pattern(path) for path in paths_b]
    for left in normalized_a:
        for right in normalized_b:
            if left == right:
                return True
            if fnmatch.fnmatch(left, right) or fnmatch.fnmatch(right, left):
                return True
            left_prefix = _prefix_before_glob(left)
            right_prefix = _prefix_before_glob(right)
            if not left_prefix or not right_prefix:
                return True
            if left_prefix.startswith(right_prefix) or right_prefix.startswith(left_prefix):
                return True
    return False


def _lock_dir(root: Path) -> Path:
    return root / ".agent" / "locks"


def _lock_path(root: Path, session_id: str) -> Path:
    return _lock_dir(root) / f"{session_id}.lock.json"


def _guard_path(root: Path) -> Path:
    return _lock_dir(root) / ".acquire.lock"


def _acquire_guard(root: Path, *, timeout_seconds: float = 10.0) -> Path:
    path = _guard_path(root)
    deadline = time.time() + timeout_seconds
    body = f"pid={os.getpid()}\n".encode("utf-8")
    while True:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            with os.fdopen(fd, "wb") as fh:
                fh.write(body)
            return path
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > 60:
                    path.unlink()
                    continue
            except OSError:
                pass
            if time.time() >= deadline:
                raise TimeoutError(f"timed out waiting for lock guard at {path}")
            time.sleep(0.02)


class AgentLockManager:
    def acquire(
        self,
        paths: str | Iterable[str],
        *,
        task: str,
        ttl_minutes: int = TTL_MINUTES_LIMIT,
        root: str | Path = ".",
    ) -> str:
        repo_root = Path(root).resolve()
        lock_dir = _lock_dir(repo_root)
        lock_dir.mkdir(parents=True, exist_ok=True)
        normalized_paths = _split_paths(paths)
        if not normalized_paths:
            raise ValueError("at least one path is required")
        if ttl_minutes <= 0:
            raise ValueError("ttl_minutes must be positive")

        guard = _acquire_guard(repo_root)
        try:
            for lock in self.list_locks(repo_root):
                other_paths = lock.get("paths")
                if not isinstance(other_paths, list):
                    continue
                if _paths_overlap(normalized_paths, [str(item) for item in other_paths]):
                    raise LockConflictError(lock)

            session_id = str(uuid.uuid4())
            now = _utc_now()
            record = {
                "v": LOCK_SCHEMA_VERSION,
                "session_id": session_id,
                "paths": normalized_paths,
                "acquired_at": _format_time(now),
                "ttl_minutes": int(ttl_minutes),
                "task": task,
                "pid": os.getpid(),
            }
            body = json.dumps(record, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            ) + b"\n"
            path = _lock_path(repo_root, session_id)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(body)
            except Exception:
                try:
                    os.close(fd)
                except OSError:
                    pass
                raise
            return session_id
        finally:
            try:
                guard.unlink()
            except OSError:
                pass

    def release(self, session_id: str, *, root: str | Path = ".") -> bool:
        repo_root = Path(root).resolve()
        path = _lock_path(repo_root, session_id)
        lock_dir = _lock_dir(repo_root).resolve()
        try:
            resolved = path.resolve()
        except OSError:
            return False
        if lock_dir not in resolved.parents:
            return False
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False

    def list_locks(
        self, root: str | Path = ".", *, include_expired: bool = False
    ) -> list[dict[str, Any]]:
        repo_root = Path(root).resolve()
        lock_dir = _lock_dir(repo_root)
        if not lock_dir.is_dir():
            return []
        locks: list[dict[str, Any]] = []
        for path in sorted(lock_dir.glob("*.lock.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            data["_path"] = path.as_posix()
            data["_mtime_ns"] = path.stat().st_mtime_ns
            if include_expired or not self._is_expired(data):
                locks.append(data)
        return locks

    def prune(
        self, root: str | Path = ".", *, stale_minutes: int | None = None
    ) -> list[str]:
        repo_root = Path(root).resolve()
        removed: list[str] = []
        now = _utc_now()
        for lock in self.list_locks(repo_root, include_expired=True):
            remove = self._is_expired(lock, now=now)
            if stale_minutes is not None:
                acquired_at = _parse_time(lock.get("acquired_at"))
                if acquired_at is not None:
                    remove = remove or acquired_at + timedelta(minutes=stale_minutes) < now
            if not remove:
                continue
            session_id = str(lock.get("session_id", ""))
            if session_id and self.release(session_id, root=repo_root):
                removed.append(session_id)
        return removed

    def check_overlap(
        self, paths: str | Iterable[str], *, root: str | Path = "."
    ) -> list[str]:
        requested = _split_paths(paths)
        conflicts: list[str] = []
        for lock in self.list_locks(root):
            lock_paths = lock.get("paths")
            if isinstance(lock_paths, list) and _paths_overlap(
                requested, [str(item) for item in lock_paths]
            ):
                conflicts.append(str(lock.get("session_id", "")))
        return [item for item in conflicts if item]

    def _is_expired(self, lock: dict[str, Any], *, now: datetime | None = None) -> bool:
        acquired_at = _parse_time(lock.get("acquired_at"))
        ttl = lock.get("ttl_minutes")
        if acquired_at is None or not isinstance(ttl, int):
            return True
        return acquired_at + timedelta(minutes=ttl) < (now or _utc_now())


def _manager() -> AgentLockManager:
    return AgentLockManager()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")

    acquire_parser = subparsers.add_parser("acquire")
    acquire_parser.add_argument("--paths", required=True)
    acquire_parser.add_argument("--task", required=True)
    acquire_parser.add_argument("--ttl-minutes", type=int, default=TTL_MINUTES_LIMIT)
    acquire_parser.add_argument("--root", default=".")

    release_parser = subparsers.add_parser("release")
    release_parser.add_argument("--session-id", required=True)
    release_parser.add_argument("--root", default=".")

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--root", default=".")
    list_parser.add_argument("--include-expired", action="store_true")
    list_parser.add_argument("--json", action="store_true")

    prune_parser = subparsers.add_parser("prune")
    prune_parser.add_argument("--root", default=".")
    prune_parser.add_argument("--stale-minutes", type=int)

    overlap_parser = subparsers.add_parser("check-overlap")
    overlap_parser.add_argument("--paths", required=True)
    overlap_parser.add_argument("--root", default=".")

    args = parser.parse_args(argv)
    manager = _manager()
    try:
        if args.command == "acquire":
            print(
                manager.acquire(
                    args.paths,
                    task=args.task,
                    ttl_minutes=args.ttl_minutes,
                    root=args.root,
                )
            )
            return 0
        if args.command == "release":
            return 0 if manager.release(args.session_id, root=args.root) else 1
        if args.command == "list":
            locks = manager.list_locks(
                args.root, include_expired=args.include_expired
            )
            if args.json:
                print(json.dumps(locks, sort_keys=True))
            else:
                for lock in locks:
                    print(
                        f"{lock.get('session_id')} "
                        f"{','.join(lock.get('paths') or [])} "
                        f"{lock.get('task')}"
                    )
            return 0
        if args.command == "prune":
            for session_id in manager.prune(
                args.root, stale_minutes=args.stale_minutes
            ):
                print(session_id)
            return 0
        if args.command == "check-overlap":
            conflicts = manager.check_overlap(args.paths, root=args.root)
            for session_id in conflicts:
                print(session_id)
            return 1 if conflicts else 0
    except LockConflictError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    parser.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
