"""Modular implementation for ``scripts/agent-sync.py``.

The single-file ``scripts/agent-sync.py`` is now a thin shim that
delegates to :func:`agent_sync.cli.main_with_exit`. Each concern lives
in its own module; the public surface re-exported here mirrors the
names that previously lived at module level on ``agent_sync.py``.
"""

from __future__ import annotations

from .codex_wrappers import command_wrapper, plan_codex_wrappers
from .cli import main, main_with_exit
from .errors import (
    EXIT_CONFLICT,
    EXIT_DIRTY,
    EXIT_LOCKED,
    EXIT_NO_PATH,
    EXIT_USAGE,
    EXIT_VALIDATION,
    ConflictError,
    DirtyError,
    LockError,
    NoPathError,
    SyncError,
    UsageError,
    VERSION_RE,
)
from .git_ops import (
    git_bytes,
    git_show,
    git_text,
    run_git,
    sha,
    tag_commit,
    tag_exists,
    tag_for,
    try_git_show,
)
from .io_utils import (
    dump_manifest,
    read_bytes,
    read_json,
    rel_path,
    write_bytes,
)
from .manifest_ops import ordered_manifest_with_sync, plan_manifest
from .merge import apply_writes, collect_orphans, plan_safe_overwrites
from .migrations import (
    expand_file_entries,
    list_migrations,
    list_tag_files,
    load_migration,
)
from .multi_hop import _execute_hop_on_temp, run_multi_hop
from .patches import plan_patches
from .preflight import acquire_lock, target_clean
from .single_hop import run_single_hop
from .sync_log import (
    append_sync_log,
    multi_hop_sync_log_entry,
    sync_log_entry,
)
from .validation import run_validation
from .versions import (
    _semver_tuple,
    compute_migration_chain,
    detect_current_version,
    validate_version,
)

__all__ = [
    "ConflictError",
    "DirtyError",
    "EXIT_CONFLICT",
    "EXIT_DIRTY",
    "EXIT_LOCKED",
    "EXIT_NO_PATH",
    "EXIT_USAGE",
    "EXIT_VALIDATION",
    "LockError",
    "NoPathError",
    "SyncError",
    "UsageError",
    "VERSION_RE",
    "_execute_hop_on_temp",
    "_semver_tuple",
    "acquire_lock",
    "append_sync_log",
    "apply_writes",
    "collect_orphans",
    "command_wrapper",
    "compute_migration_chain",
    "detect_current_version",
    "dump_manifest",
    "expand_file_entries",
    "git_bytes",
    "git_show",
    "git_text",
    "list_migrations",
    "list_tag_files",
    "load_migration",
    "main",
    "main_with_exit",
    "multi_hop_sync_log_entry",
    "ordered_manifest_with_sync",
    "plan_codex_wrappers",
    "plan_manifest",
    "plan_patches",
    "plan_safe_overwrites",
    "read_bytes",
    "read_json",
    "rel_path",
    "run_git",
    "run_multi_hop",
    "run_single_hop",
    "run_validation",
    "sha",
    "sync_log_entry",
    "tag_commit",
    "tag_exists",
    "tag_for",
    "target_clean",
    "try_git_show",
    "validate_version",
    "write_bytes",
]
