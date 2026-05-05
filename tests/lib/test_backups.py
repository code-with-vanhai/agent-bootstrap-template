#!/usr/bin/env python3
"""Plan D-9 contract tests for ``agent_sync.backups``.

Locks down the fallback chain end-to-end across all four entry points
(``create_backup`` / ``list_backups`` / ``prune_backups`` /
``restore_backup``) so a regression like the one in the Stage 1+2
review — where only the write side honored the fallback while the read
side still pointed at the unwritable ``$XDG_CACHE_HOME`` — is caught
automatically. Plan reference: ``docs/2026-05-05-migration-ux-improvement-plan.md`` D-9 (line 843) and the test-delta entry at line 863.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))

from agent_sync import backups as B  # noqa: E402


def _seed_target(tmp: Path) -> Path:
    """Copy the 0.3.0 fixture and turn it into a clean git worktree."""

    target = tmp / "target"
    shutil.copytree(REPO_ROOT / "tests/migrations/0.3.0/after", target)
    subprocess.check_call(["git", "init", "-q", str(target)])
    subprocess.check_call(
        [
            "git",
            "-C",
            str(target),
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "add",
            "-A",
        ]
    )
    subprocess.check_call(
        [
            "git",
            "-C",
            str(target),
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-q",
            "-m",
            "seed",
        ]
    )
    return target


class _IsolatedHomeMixin(unittest.TestCase):
    """Redirect $HOME (and clear $XDG_CACHE_HOME by default) for each test.

    Keeps the developer's real ``~/.cache/agent-bootstrap`` untouched —
    the fallback chain only touches a per-test temp directory.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.fake_home = self.tmp / "home"
        self.fake_home.mkdir()
        self._env_backup = {
            k: os.environ.get(k) for k in ("HOME", "XDG_CACHE_HOME")
        }
        os.environ["HOME"] = str(self.fake_home)
        os.environ.pop("XDG_CACHE_HOME", None)

    def tearDown(self) -> None:
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class FallbackRoundTripTests(_IsolatedHomeMixin):
    def test_round_trip_when_xdg_unwritable_falls_back_to_home_cache(self) -> None:
        """create→list→restore must all land on ``~/.cache`` when XDG fails."""

        os.environ["XDG_CACHE_HOME"] = "/dev/null/agent-cache"
        target = _seed_target(self.tmp)
        original = (target / ".agent" / "manifest.json").read_bytes()

        # Create — should fall back, with a stderr warning for the user.
        backup_dir, backup_id, _ = B.create_backup(
            target=target,
            from_version="0.3.0",
            to_version="0.4.0",
            writes={".agent/manifest.json": original + b"\n"},
            mode="single-hop",
        )
        self.assertTrue(
            str(backup_dir).startswith(str(self.fake_home / ".cache")),
            f"create_backup should land under ~/.cache fallback; got {backup_dir}",
        )

        # List — must see the row that create just wrote, not [].
        rows = B.list_backups(target)
        self.assertEqual(
            [r[0] for r in rows],
            [backup_id],
            "list_backups must honor D-9 fallback (regression guard for "
            "review High-1: read side ignored fallback)",
        )

        # Mutate the file the migration "wrote" so restore has work to do.
        (target / ".agent" / "manifest.json").write_bytes(b"mutated\n")
        subprocess.check_call(
            [
                "git",
                "-C",
                str(target),
                "-c",
                "user.email=t@t",
                "-c",
                "user.name=t",
                "commit",
                "-aq",
                "-m",
                "apply",
            ]
        )

        # Restore — must locate the backup under the fallback root.
        restored_dir, count = B.restore_backup(target, backup_id)
        self.assertTrue(
            str(restored_dir).startswith(str(self.fake_home / ".cache")),
            restored_dir,
        )
        self.assertGreaterEqual(count, 1)
        self.assertEqual(
            (target / ".agent" / "manifest.json").read_bytes(),
            original,
            "restored file must be byte-identical to the pre-apply snapshot",
        )

    def test_prune_in_fallback_root_respects_keep(self) -> None:
        """``prune_backups`` walks the same chain create_backup landed on."""

        os.environ["XDG_CACHE_HOME"] = "/dev/null/agent-cache"
        target = _seed_target(self.tmp)

        for i in range(4):
            B.create_backup(
                target=target,
                from_version="0.3.0",
                to_version=f"0.4.{i}",
                writes={".agent/manifest.json": f"v{i}\n".encode()},
                mode="single-hop",
            )
        # All four should be visible from list (proves create→list parity).
        self.assertEqual(len(B.list_backups(target)), 4)

        pruned = B.prune_backups(target, keep=2)
        self.assertEqual(
            len(pruned),
            2,
            "prune must operate on the fallback root, not the unwritable "
            "primary; otherwise it silently no-ops and ~/.cache grows.",
        )
        self.assertEqual(len(B.list_backups(target)), 2)


class FallbackErrorTests(_IsolatedHomeMixin):
    def test_both_xdg_and_home_unwritable_raises_actionable_error(self) -> None:
        """Plan D-9: when *every* candidate fails, raise with all paths tried."""

        # Point both XDG and ~/.cache at unwritable paths.
        os.environ["XDG_CACHE_HOME"] = "/dev/null/agent-cache"
        # Replace fake_home with one whose .cache is a regular file -> mkdir
        # under it raises NotADirectoryError, exercising the second-failure
        # branch of ``_resolve_writable_root``.
        cache_blocker = self.fake_home / ".cache"
        cache_blocker.write_text("not a dir")

        target = _seed_target(self.tmp)
        with self.assertRaises(B.BackupError) as ctx:
            B.create_backup(
                target=target,
                from_version="0.3.0",
                to_version="0.4.0",
                writes={".agent/manifest.json": b"x"},
                mode="single-hop",
            )
        msg = str(ctx.exception)
        self.assertIn("/dev/null/agent-cache", msg)
        self.assertIn(str(cache_blocker), msg)
        self.assertIn("--backup-dir", msg)


if __name__ == "__main__":
    unittest.main()
