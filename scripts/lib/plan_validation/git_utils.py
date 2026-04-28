from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional


def _git(repo_root: Path, *args: str) -> Optional[bytes]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _ref_exists(repo_root: Path, ref: str) -> bool:
    out = _git(repo_root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    return out is not None and bool(out.strip())


def _show_at_ref(repo_root: Path, ref: str, path: str) -> Optional[str]:
    out = _git(repo_root, "show", f"{ref}:{path}")
    if out is None:
        return None
    return out.decode("utf-8", errors="replace")
