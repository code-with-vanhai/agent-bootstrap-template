"""Path-relative-safety, byte read/write, and JSON helpers.

These wrap every filesystem touch inside the sync runner so:
  - ``..`` and absolute paths are rejected before any disk write
    (:func:`rel_path` is the load-bearing safety check),
  - ``read_bytes`` returns ``None`` on missing-file (so the planner can
    distinguish "not yet present" from "empty"), and
  - ``read_json`` preserves key order via ``object_pairs_hook=OrderedDict``
    so ``ordered_manifest_with_sync`` can re-emit a stable manifest.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path

from .errors import UsageError


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
