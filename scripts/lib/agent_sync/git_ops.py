"""Subprocess wrappers around ``git`` plus tag/commit helpers.

Every git invocation in the sync runner goes through here so that:
  - failures consistently raise :class:`SyncError` with the captured
    stderr (instead of silently returning a non-zero ``CompletedProcess``),
  - the ``-C <repo>`` arg pattern is applied uniformly, and
  - tag / commit / blob lookups have a single source of truth for the
    ``v<version>`` naming convention.
"""

from __future__ import annotations

import hashlib
import subprocess

from .errors import SyncError, UsageError


def run_git(repo, *args, check=True, text=False):
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=text,
    )
    if check and result.returncode != 0:
        stderr = (
            result.stderr.strip()
            if text
            else result.stderr.decode("utf-8", "replace").strip()
        )
        raise SyncError(f"git {' '.join(args)} failed: {stderr}")
    return result


def git_text(repo, *args):
    return run_git(repo, *args, text=True).stdout


def git_bytes(repo, *args, check=True):
    return run_git(repo, *args, check=check, text=False)


def tag_for(version):
    return f"v{version}"


def tag_exists(repo, version):
    tag = tag_for(version)
    result = run_git(
        repo, "rev-parse", "--verify", "--quiet", f"{tag}^{{commit}}", check=False
    )
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
        raise UsageError(
            f"migration references missing source at {tag}:{source_path}: {stderr}"
        )
    return None


def try_git_show(repo, version, source_path):
    """Stage 3.2: non-raising alias for ``git_show(required=False)``.

    Returns ``None`` whenever the byte read cannot complete — either
    because ``v<version>`` does not exist (e.g. ephemeral mirror
    missing the tag) or because ``source_path`` did not exist at that
    tag. Callers that already handle either failure identically should
    use this name to make the intent obvious at the call site.
    """
    return git_show(repo, version, source_path, required=False)


def sha(data):
    if data is None:
        return "missing"
    return hashlib.sha256(data).hexdigest()
