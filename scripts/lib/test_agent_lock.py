"""Tests for scripts/lib/agent_lock.py."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.lib import agent_lock


class AgentLockTests(unittest.TestCase):
    def make_root(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="agent-lock-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def manager(self) -> agent_lock.AgentLockManager:
        return agent_lock.AgentLockManager()

    def test_acquire_creates_lock_file(self) -> None:
        root = self.make_root()
        session = self.manager().acquire(
            ["src/auth/**"], task="test", ttl_minutes=60, root=root
        )

        lock_files = list((root / ".agent" / "locks").glob("*.lock.json"))
        self.assertEqual(len(lock_files), 1)
        self.assertEqual(lock_files[0].stem, session + ".lock")
        payload = json.loads(lock_files[0].read_text(encoding="utf-8"))
        self.assertEqual(payload["paths"], ["src/auth/**"])

    def test_overlapping_active_lock_conflicts(self) -> None:
        root = self.make_root()
        manager = self.manager()
        first = manager.acquire(["src/auth/**"], task="first", root=root)

        with self.assertRaises(agent_lock.LockConflictError) as ctx:
            manager.acquire(["src/auth/login.ts"], task="second", root=root)

        self.assertEqual(ctx.exception.lock["session_id"], first)
        self.assertEqual(len(list((root / ".agent" / "locks").glob("*.lock.json"))), 1)

    def test_release_known_and_unknown_session(self) -> None:
        root = self.make_root()
        manager = self.manager()
        session = manager.acquire(["src/**"], task="test", root=root)

        self.assertTrue(manager.release(session, root=root))
        self.assertFalse(manager.release(session, root=root))

    def test_expired_locks_are_ignored_and_pruned(self) -> None:
        root = self.make_root()
        manager = self.manager()
        expired = manager.acquire(["src/**"], task="old", root=root, ttl_minutes=1)
        active = manager.acquire(["tests/**"], task="new", root=root, ttl_minutes=60)
        path = root / ".agent" / "locks" / f"{expired}.lock.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["acquired_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=2)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        path.write_text(json.dumps(payload), encoding="utf-8")

        self.assertEqual(manager.check_overlap(["src/file.py"], root=root), [])
        self.assertEqual(manager.prune(root), [expired])
        self.assertTrue((root / ".agent" / "locks" / f"{active}.lock.json").exists())

    def test_list_json_excludes_expired_by_default(self) -> None:
        root = self.make_root()
        manager = self.manager()
        session = manager.acquire(["src/**"], task="old", root=root, ttl_minutes=1)
        path = root / ".agent" / "locks" / f"{session}.lock.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["acquired_at"] = "2000-01-01T00:00:00Z"
        path.write_text(json.dumps(payload), encoding="utf-8")

        self.assertEqual(manager.list_locks(root), [])
        self.assertEqual(len(manager.list_locks(root, include_expired=True)), 1)

    def test_threaded_same_path_acquire_has_single_winner(self) -> None:
        root = self.make_root()
        results: list[str] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def acquire_one(index: int) -> None:
            try:
                session = self.manager().acquire(
                    ["src/auth/**"], task=f"task-{index}", root=root
                )
                with lock:
                    results.append(session)
            except Exception as exc:  # noqa: BLE001 - test records all losers
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=acquire_one, args=(index,)) for index in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 7)
        self.assertTrue(all(isinstance(exc, agent_lock.LockConflictError) for exc in errors))

    def test_windows_style_paths_are_normalized_for_overlap(self) -> None:
        self.assertTrue(
            agent_lock._paths_overlap(["src\\auth\\login.ts"], ["src/auth/**"])
        )

    def test_cli_acquire_release_and_conflict_codes(self) -> None:
        root = self.make_root()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = agent_lock.main(
                [
                    "acquire",
                    "--root",
                    str(root),
                    "--paths",
                    "src/**",
                    "--task",
                    "cli",
                ]
            )
        self.assertEqual(rc, 0)
        session = stdout.getvalue().strip()

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            conflict_rc = agent_lock.main(
                [
                    "acquire",
                    "--root",
                    str(root),
                    "--paths",
                    "src/file.py",
                    "--task",
                    "conflict",
                ]
            )
        self.assertEqual(conflict_rc, 1)
        self.assertIn(session, stderr.getvalue())

        self.assertEqual(
            agent_lock.main(["release", "--root", str(root), "--session-id", session]),
            0,
        )
        self.assertEqual(
            agent_lock.main(["release", "--root", str(root), "--session-id", session]),
            1,
        )


if __name__ == "__main__":
    unittest.main()
