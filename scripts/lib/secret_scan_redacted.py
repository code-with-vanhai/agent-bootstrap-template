#!/usr/bin/env python3
"""Small redacted secret scanner used when gitleaks is unavailable.

The scanner is intentionally conservative and never prints matched values.
Findings are emitted as:

    FINDING: path:line [PATTERN_NAME]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence


MAX_FILE_BYTES = 1_048_576
EXCLUDE_DIRS = frozenset(
    {
        ".git",
        "build",
        "dist",
        "node_modules",
        "__pycache__",
    }
)
ALLOW_MARKERS = (
    "# agent-secret-scan:allow",
    "<!-- agent-secret-scan:allow -->",
)


@dataclass(frozen=True)
class SecretPattern:
    name: str
    regex: re.Pattern[str]


PATTERNS: tuple[SecretPattern, ...] = (
    SecretPattern(
        "AWS_ACCESS_KEY_ID",
        re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    ),
    SecretPattern(
        "GITHUB_TOKEN",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{36,255}\b"),
    ),
    SecretPattern(
        "SLACK_TOKEN",
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    ),
    SecretPattern(
        "STRIPE_LIVE_KEY",
        re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}\b"),
    ),
    SecretPattern(
        "PRIVATE_KEY",
        re.compile(
            r"-----BEGIN (?:RSA |DSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"
        ),
    ),
    SecretPattern(
        "GENERIC_SECRET_ASSIGNMENT",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|token|password|passwd)\b"
            r"\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{32,}"
        ),
    ),
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    pattern: str


def _is_allowlisted(line: str) -> bool:
    return any(marker in line for marker in ALLOW_MARKERS)


def _excluded(parts: Sequence[str]) -> bool:
    return any(part in EXCLUDE_DIRS for part in parts)


def _iter_files(root: Path) -> Iterator[Path]:
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        rel_parts = current_path.relative_to(root).parts
        if _excluded(rel_parts):
            dirs[:] = []
            continue
        dirs[:] = [
            name
            for name in dirs
            if name not in EXCLUDE_DIRS and not (current_path / name).is_symlink()
        ]
        for filename in files:
            path = current_path / filename
            if path.is_symlink():
                continue
            yield path


def scan_file(path: Path, *, root: Path) -> list[Finding]:
    try:
        stat = path.stat()
    except OSError:
        return []
    if stat.st_size > MAX_FILE_BYTES:
        return []

    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []

    rel = path.relative_to(root).as_posix()
    findings: list[Finding] = []
    for line_no, line in enumerate(lines, start=1):
        if _is_allowlisted(line):
            continue
        for pattern in PATTERNS:
            if pattern.regex.search(line):
                findings.append(Finding(rel, line_no, pattern.name))
                break
    return findings


def scan(root: Path) -> list[Finding]:
    resolved = root.resolve()
    findings: list[Finding] = []
    for path in _iter_files(resolved):
        findings.extend(scan_file(path, root=resolved))
    return findings


def format_findings(findings: Iterable[Finding]) -> list[str]:
    return [
        f"FINDING: {finding.path}:{finding.line} [{finding.pattern}]"
        for finding in findings
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="repository root to scan")
    args = parser.parse_args(argv)

    root = Path(args.root)
    findings = scan(root)
    for line in format_findings(findings):
        print(line)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
