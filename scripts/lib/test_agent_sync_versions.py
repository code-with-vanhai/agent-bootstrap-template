"""Tests for ``agent_sync.versions``: BFS migration-chain topology.

Regression-proofs the post-0.12.0 audit finding H-3 fix in
``core/migrations/1.0.0/migration.json``: tightening
``from_versions: ["0.11.0"]`` to ``["0.12.0"]`` removed the
dual-source-from-``0.11.0`` BFS bypass that would otherwise let
``0.11.0 → 1.0.0`` skip the ``0.12.0`` hop entirely (because
``compute_migration_chain`` deterministically returns the shortest path).

Two layers of coverage:

  - **Live-topology assertions** against the repo's real
    ``core/migrations/`` tree, locking the canonical chain
    ``0.10.0 → 0.11.0 → 0.12.0 → 1.0.0`` and the empty-chain
    ``current == to`` shortcut.

  - **Synthetic-topology assertions** that build a controlled migration
    tree in a tempdir, exercising both the OLD bug shape (parallel
    edges from ``0.11.0`` to ``0.12.0`` *and* ``1.0.0``) and the
    FIXED shape (``1.0.0`` reachable only from ``0.12.0``). The
    synthetic test makes the BFS-bypass behavior structural rather than
    incidental to the live tree, so the regression survives any future
    legitimate edge additions in ``core/migrations/``.
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))

from agent_sync.errors import NoPathError  # noqa: E402
from agent_sync.versions import compute_migration_chain  # noqa: E402


def _write_migration(
    template_root: pathlib.Path,
    version: str,
    from_versions: list[str],
) -> None:
    """Write a minimal valid ``migration.json`` for synthetic tests.

    Only the keys the BFS reads (``schema_version``, ``to``,
    ``from_versions``) are required to be correct; the rest are stubs
    that satisfy any down-the-line readers.
    """

    migration_dir = template_root / "core" / "migrations" / version
    migration_dir.mkdir(parents=True, exist_ok=True)
    (migration_dir / "migration.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "version": version,
                "from_versions": from_versions,
                "to": version,
                "safe_overwrite": [],
                "patches": [],
                "manifest_updates": {},
            }
        ),
        encoding="utf-8",
    )


class LiveTopologyTests(unittest.TestCase):
    """Lock the real ``core/migrations/`` topology against regressions."""

    def test_same_version_returns_empty_chain(self) -> None:
        self.assertEqual(
            compute_migration_chain(REPO_ROOT, "1.0.0", "1.0.0"), []
        )

    def test_single_hop_0_11_0_to_0_12_0(self) -> None:
        self.assertEqual(
            compute_migration_chain(REPO_ROOT, "0.11.0", "0.12.0"),
            ["0.12.0"],
        )

    def test_0_11_0_to_1_0_0_must_pass_through_0_12_0(self) -> None:
        """Auditor finding H-3 regression guard.

        Before the fix both ``0.12.0`` and ``1.0.0`` declared
        ``from_versions=["0.11.0"]``, so BFS returned the length-1
        chain ``["1.0.0"]`` and bypassed ``0.12.0`` entirely. After
        tightening ``1.0.0/from_versions`` to ``["0.12.0"]`` the only
        reachable path from ``0.11.0`` to ``1.0.0`` is the length-2
        chain through ``0.12.0``.
        """

        chain = compute_migration_chain(REPO_ROOT, "0.11.0", "1.0.0")
        self.assertEqual(chain, ["0.12.0", "1.0.0"])
        self.assertIn(
            "0.12.0",
            chain,
            msg=(
                "BFS bypassed 0.12.0 on 0.11.0 → 1.0.0 — auditor "
                "finding H-3 regressed. Verify "
                "core/migrations/1.0.0/migration.json::from_versions "
                "is exactly [\"0.12.0\"]."
            ),
        )

    def test_full_canonical_chain_0_10_0_to_1_0_0(self) -> None:
        self.assertEqual(
            compute_migration_chain(REPO_ROOT, "0.10.0", "1.0.0"),
            ["0.11.0", "0.12.0", "1.0.0"],
        )

    def test_no_path_raises(self) -> None:
        with self.assertRaises(NoPathError):
            compute_migration_chain(REPO_ROOT, "1.0.0", "0.10.0")


class SyntheticTopologyTests(unittest.TestCase):
    """Build controlled trees so BFS preference is provable structurally."""

    def test_old_h3_shape_reproduces_bypass(self) -> None:
        """With BOTH 0.12.0 and 1.0.0 sourcing from 0.11.0, BFS picks
        the length-1 direct edge — this is the bug auditor finding H-3
        flagged. The synthetic shape proves the bypass is structural,
        not incidental to the live tree.
        """

        with tempfile.TemporaryDirectory() as tmp:
            template = pathlib.Path(tmp)
            _write_migration(template, "0.12.0", ["0.11.0"])
            _write_migration(template, "1.0.0", ["0.11.0"])
            self.assertEqual(
                compute_migration_chain(template, "0.11.0", "1.0.0"),
                ["1.0.0"],
                msg=(
                    "Synthetic OLD-shape sanity check failed: BFS "
                    "should pick the length-1 direct edge here."
                ),
            )

    def test_fixed_shape_forces_chain_through_0_12_0(self) -> None:
        """Mirroring the post-fix live topology: 1.0.0 reachable only
        from 0.12.0. BFS now returns the length-2 chain.
        """

        with tempfile.TemporaryDirectory() as tmp:
            template = pathlib.Path(tmp)
            _write_migration(template, "0.12.0", ["0.11.0"])
            _write_migration(template, "1.0.0", ["0.12.0"])
            self.assertEqual(
                compute_migration_chain(template, "0.11.0", "1.0.0"),
                ["0.12.0", "1.0.0"],
            )

    def test_bfs_prefers_shortest_then_lowest_semver_tiebreak(self) -> None:
        """When two equal-length paths exist, BFS tie-breaks on the
        next-hop's lowest semver tuple (matches ``versions.py`` docstring
        and the ``_semver_tuple`` sort in adjacency normalisation).
        """

        with tempfile.TemporaryDirectory() as tmp:
            template = pathlib.Path(tmp)
            _write_migration(template, "0.12.0", ["0.11.0"])
            _write_migration(template, "0.13.0", ["0.11.0"])
            _write_migration(template, "1.0.0", ["0.12.0", "0.13.0"])
            self.assertEqual(
                compute_migration_chain(template, "0.11.0", "1.0.0"),
                ["0.12.0", "1.0.0"],
            )


if __name__ == "__main__":
    unittest.main()
