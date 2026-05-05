"""Argparse + dispatch entrypoint for the sync runner.

Public CLI is a frozen contract: the migration fixture suite invokes
``scripts/agent-sync.sh`` (which ``exec``s this entry) with a fixed flag
set, so adding/removing/renaming any flag here breaks downstream sync
workflows.

``main_with_exit`` wraps ``main`` to translate :class:`SyncError`
subclasses into the matching exit code (the shim at
``scripts/agent-sync.py`` calls this so the ``__main__`` block stays
trivial).

Stage 1 of the 2026-05-05 migration UX plan adds these flags without
breaking the existing surface:

  - ``--no-auto-multi-hop``: opt out of single-hop's auto fallback
  - ``--backup``: opt-in pre-apply snapshot in an external cache
  - ``--backup-dir``: override $XDG_CACHE_HOME for tests / power users
  - ``--backup-keep``: retention count (default 5)
  - ``--verbose``: force preflight summary even on non-TTY stdout
  - ``backups`` subcommand: ``list``, ``restore <id>``, ``prune``
  - ``doctor`` subcommand: read-only diagnostics (``--json`` optional)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .errors import SyncError, UsageError
from .io_utils import rel_path


def _add_sync_arguments(parser):
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
        help=(
            "Walk a deterministic chain of single-hop migrations from the target's "
            "current version up to --to. Dry-run by default; --apply rehearses on a "
            "temp clone before touching the target."
        ),
    )
    parser.add_argument(
        "--no-auto-multi-hop",
        action="store_true",
        help=(
            "Disable Stage 1.1 auto-fallback. When the requested --to is not "
            "directly reachable from the current version, fail with NoPathError "
            "instead of automatically walking a chain."
        ),
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help=(
            "Snapshot pre-apply file contents into "
            "$XDG_CACHE_HOME/agent-bootstrap/backups (default off). The backup "
            "lives outside the target repo so .gitignore stays untouched."
        ),
    )
    parser.add_argument(
        "--backup-dir",
        help=(
            "Override the backup root. Defaults to "
            "$XDG_CACHE_HOME/agent-bootstrap/backups (or ~/.cache/...)."
        ),
    )
    parser.add_argument(
        "--backup-keep",
        type=int,
        default=None,
        help="Retention count when --backup is set. Default 5.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Force preflight summary on non-TTY stdout (e.g. CI logs).",
    )


def _build_root_parser():
    parser = argparse.ArgumentParser(
        description="Sync an Agent Bootstrap Kit target repository to a template version."
    )
    parser.add_argument("--template-root", required=True)
    return parser


def _is_doctor_command(argv):
    """True when the first positional (after ``--template-root``) is ``doctor``."""

    skip_next = False
    for token in argv:
        if skip_next:
            skip_next = False
            continue
        if token.startswith("--template-root="):
            continue
        if token == "--template-root":
            skip_next = True
            continue
        if token.startswith("-"):
            continue
        return token == "doctor"
    return False


def _is_backups_command(argv):
    """Return True iff the first positional non-flag arg is ``backups``.

    We can't use argparse subparsers cleanly because ``--target`` is
    required at the top level for the legacy single-hop / multi-hop
    surface. The shim ``scripts/agent-sync.sh`` always prepends
    ``--template-root <path>`` before user args, so we have to skip
    that pair when scanning for the subcommand token.
    """

    skip_next = False
    for token in argv:
        if skip_next:
            skip_next = False
            continue
        if token.startswith("--template-root="):
            continue
        if token == "--template-root":
            skip_next = True
            continue
        if token.startswith("-"):
            continue
        return token == "backups"
    return False


def _run_doctor_subcommand(argv):
    parser = argparse.ArgumentParser(prog="agent-sync.sh doctor")
    parser.add_argument("--template-root", required=True)
    parser.add_argument("subcommand_marker", choices=["doctor"])
    parser.add_argument("--target", required=True)
    parser.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    from .doctor import run_doctor  # noqa: WPS433

    return run_doctor(
        template_root=Path(args.template_root).resolve(),
        target=Path(args.target).resolve(),
        as_json=args.json,
    )


def _run_backups_subcommand(argv):
    parser = argparse.ArgumentParser(prog="agent-sync.sh backups")
    parser.add_argument("--template-root", required=True)
    parser.add_argument("subcommand_marker", choices=["backups"])
    sub = parser.add_subparsers(dest="action")

    list_p = sub.add_parser("list")
    list_p.add_argument("--target", required=True)
    list_p.add_argument("--backup-dir")

    restore_p = sub.add_parser("restore")
    restore_p.add_argument("backup_id")
    restore_p.add_argument("--target", required=True)
    restore_p.add_argument("--backup-dir")

    prune_p = sub.add_parser("prune")
    prune_p.add_argument("--target", required=True)
    prune_p.add_argument("--backup-dir")
    prune_p.add_argument("--keep", type=int, default=None)

    args = parser.parse_args(argv)
    if not args.action:
        raise UsageError(
            "backups subcommand requires one of: list, restore <id>, prune"
        )

    from .backups import cmd_list, cmd_prune, cmd_restore  # noqa: WPS433

    if args.action == "list":
        return cmd_list(args)
    if args.action == "restore":
        return cmd_restore(args)
    if args.action == "prune":
        return cmd_prune(args)
    raise UsageError(f"unknown backups subcommand: {args.action}")


def main(argv):
    if _is_doctor_command(argv):
        return _run_doctor_subcommand(argv)
    if _is_backups_command(argv):
        return _run_backups_subcommand(argv)

    from .multi_hop import run_multi_hop  # noqa: WPS433
    from .single_hop import run_single_hop  # noqa: WPS433

    parser = argparse.ArgumentParser(
        description="Sync an Agent Bootstrap Kit target repository to a template version."
    )
    _add_sync_arguments(parser)
    args = parser.parse_args(argv)

    template_root = Path(args.template_root).resolve()
    target = Path(args.target).resolve()
    accept_theirs = {rel_path(path) for path in args.accept_theirs}

    if not (template_root / ".git").exists():
        raise UsageError(f"template root is not a git repo: {template_root}")
    if sys.version_info < (3, 8):
        raise UsageError("python3 >= 3.8 is required")

    if args.multi_hop:
        return run_multi_hop(args, template_root, target, accept_theirs)
    return run_single_hop(args, template_root, target, accept_theirs)


def main_with_exit(argv=None):
    """Translate SyncError -> exit code; called by the script shim."""
    if argv is None:
        argv = sys.argv[1:]
    try:
        return main(argv)
    except SyncError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return exc.exit_code
