"""Argparse + dispatch entrypoint for the sync runner.

Public CLI is a frozen contract: the migration fixture suite invokes
``scripts/agent-sync.sh`` (which ``exec``s this entry) with a fixed flag
set, so adding/removing/renaming any flag here breaks downstream sync
workflows.

``main_with_exit`` wraps ``main`` to translate :class:`SyncError`
subclasses into the matching exit code (the shim at
``scripts/agent-sync.py`` calls this so the ``__main__`` block stays
trivial).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .errors import SyncError, UsageError
from .io_utils import rel_path
from .multi_hop import run_multi_hop
from .single_hop import run_single_hop


def main(argv):
    parser = argparse.ArgumentParser(
        description="Sync an Agent Bootstrap Kit target repository to a template version."
    )
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
