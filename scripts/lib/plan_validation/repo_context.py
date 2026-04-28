from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from .models import RepoContext


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


_SEMVER_NUMERIC = re.compile(r"(\d+)")


def _react_major_version(spec: str) -> Optional[int]:
    if not spec:
        return None
    match = _SEMVER_NUMERIC.search(spec)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def detect_repo_context(repo_root: Path) -> RepoContext:
    ctx = RepoContext(repo_root=repo_root)

    package_json = _read_json(repo_root / "package.json") or {}
    deps = {}
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        deps.update(package_json.get(section, {}) or {})

    react_spec = deps.get("react")
    if react_spec:
        ctx.react_version = react_spec

    # MV3 detection: any of the signals counts.
    if "@types/chrome" in deps:
        ctx.is_mv3_extension = True
        ctx.detected_signals.append("package.json: @types/chrome")

    if (repo_root / "wxt.config.ts").is_file() or (repo_root / "wxt.config.js").is_file():
        ctx.is_mv3_extension = True
        ctx.detected_signals.append("wxt.config present")

    for manifest_candidate in (
        repo_root / "manifest.json",
        repo_root / "public" / "manifest.json",
        repo_root / "src" / "manifest.json",
    ):
        manifest = _read_json(manifest_candidate)
        if manifest and manifest.get("manifest_version") == 3:
            ctx.is_mv3_extension = True
            ctx.detected_signals.append(f"{manifest_candidate.name}: manifest_version=3")
            break

    # Test setup mocking chrome.runtime.
    test_setup_globs = (
        repo_root / "__tests__" / "setup.ts",
        repo_root / "__tests__" / "setup.js",
        repo_root / "tests" / "setup.ts",
        repo_root / "test" / "setup.ts",
        repo_root / "vitest.setup.ts",
    )
    for setup in test_setup_globs:
        if setup.is_file():
            try:
                content = setup.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "chrome.runtime" in content or "chromeRuntime" in content:
                ctx.is_mv3_extension = True
                ctx.detected_signals.append(f"{setup.name}: mocks chrome.runtime")
                break

    return ctx
