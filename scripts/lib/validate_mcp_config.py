#!/usr/bin/env python3
"""Validate MCP client configuration files for inline credentials.

Scope (Stage 5, opt-in):

- ``catalog.json`` — schema check for ``core/mcp/catalog.json`` when run from
  the template repo. Always validated when present.
- ``.mcp.json`` — linted when present in the working directory or
  ``--root``. The default bootstrap NEVER creates this file.
- ``.mcp.json.suggested`` — linted when present. The bootstrap creates this
  file only when run with ``--with-mcp-discovery``; the file is a draft for
  human review and is not active until the user promotes it manually.

The validator is intentionally conservative:

- It refuses configurations that embed obvious tokens
  (``sk-…``, ``ghp_…``, ``github_pat_…``, ``xoxb-…``, ``xoxp-…``).
- It refuses long high-entropy literals when they appear as values for
  auth-looking keys (``token``, ``api_key``, ``password``, ``secret``, ``auth``).
- It accepts environment-variable references such as ``${GITHUB_TOKEN}``,
  ``$GITHUB_TOKEN``, or empty strings as a placeholder.
- It does not network, does not invoke MCP servers, and does not need any
  third-party dependency.

Exit codes:

- ``0`` — nothing to do (no config files present), or all present files passed.
- ``1`` — at least one finding requires the user's attention.
- ``2`` — usage / IO error.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import re
import sys
from typing import Iterable

INLINE_TOKEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai-key", re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b")),
    ("github-pat-classic", re.compile(r"\bghp_[A-Za-z0-9]{20,}\b")),
    ("github-pat-fine-grained", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("slack-bot", re.compile(r"\bxoxb-[A-Za-z0-9-]{10,}\b")),
    ("slack-user", re.compile(r"\bxoxp-[A-Za-z0-9-]{10,}\b")),
)

# Substring matches; lowercase. Used to decide whether a high-entropy literal
# should be treated as a credential candidate. Kept tight to avoid noisy
# false positives in non-auth fields like description text.
AUTH_KEY_SUBSTRINGS: tuple[str, ...] = (
    "token",
    "api_key",
    "apikey",
    "password",
    "secret",
    "auth",
    "credential",
    "private_key",
    "privatekey",
    "client_secret",
    "clientsecret",
)

# Accept either ``${VAR}`` or ``$VAR`` exactly. The previous pattern
# ``\$\{?…\}?`` matched ``${VAR`` and ``$VAR}`` because the braces were
# independently optional; that let malformed placeholders sneak through
# the inline-credential check on auth-looking keys.
ENV_REF_RE = re.compile(
    r"^(?:\$\{[A-Z_][A-Z0-9_]*\}|\$[A-Z_][A-Z0-9_]*)$"
)
# POSIX-style environment variable name; mirrors the matched group above
# so the catalog validator and the placeholder check use one rule.
ENV_VAR_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
# Auth-header value prefixes that conventionally precede a single token
# (RFC 6750 Bearer, RFC 7617 Basic, GitHub-style ``Token …``). When we
# see one of these on an auth-looking field, strip it and re-evaluate
# the trailing token; otherwise high-entropy literals can hide behind
# the prefix's whitespace and bypass the prose-skip heuristic.
AUTH_HEADER_PREFIX_RE = re.compile(
    r"^\s*(?:Bearer|Basic|Token|OAuth|Digest)\s+",
    re.IGNORECASE,
)
ENTROPY_MIN_LEN = 24
ENTROPY_MIN_BITS = 3.5


class Finding:
    __slots__ = ("path", "key_path", "message")

    def __init__(self, path: pathlib.Path, key_path: str, message: str) -> None:
        self.path = path
        self.key_path = key_path
        self.message = message

    def render(self, root: pathlib.Path) -> str:
        try:
            rel = self.path.relative_to(root)
        except ValueError:
            rel = self.path
        return f"  {rel}::{self.key_path} — {self.message}"


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts: dict[str, int] = {}
    for char in value:
        counts[char] = counts.get(char, 0) + 1
    total = float(len(value))
    entropy = 0.0
    for count in counts.values():
        probability = count / total
        entropy -= probability * math.log2(probability)
    return entropy


def is_env_reference(value: str) -> bool:
    stripped = value.strip()
    if stripped == "":
        return True
    return bool(ENV_REF_RE.match(stripped))


def looks_like_auth_key(key: str) -> bool:
    lowered = key.lower()
    return any(substr in lowered for substr in AUTH_KEY_SUBSTRINGS)


def scan_value(
    *,
    file_path: pathlib.Path,
    key_path: str,
    parent_key: str,
    value: object,
    findings: list[Finding],
) -> None:
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            child_path = f"{key_path}.{child_key}" if key_path else child_key
            scan_value(
                file_path=file_path,
                key_path=child_path,
                parent_key=str(child_key),
                value=child_value,
                findings=findings,
            )
        return

    if isinstance(value, list):
        for index, item in enumerate(value):
            child_path = f"{key_path}[{index}]"
            scan_value(
                file_path=file_path,
                key_path=child_path,
                parent_key=parent_key,
                value=item,
                findings=findings,
            )
        return

    if not isinstance(value, str):
        return

    for label, pattern in INLINE_TOKEN_PATTERNS:
        if pattern.search(value):
            findings.append(
                Finding(
                    file_path,
                    key_path or parent_key,
                    f"inline credential detected ({label}); use an env var reference instead",
                )
            )
            return

    if looks_like_auth_key(parent_key) and not is_env_reference(value):
        # Skip explicit comment keys (we use the ``_comment_*`` convention).
        if parent_key.startswith("_") or "comment" in parent_key.lower():
            return
        # Strip a leading auth-header prefix once so values like
        # ``Authorization: "Bearer <token>"`` get scanned as the trailing
        # token rather than as multi-word prose.
        stripped = AUTH_HEADER_PREFIX_RE.sub("", value, count=1)
        # If the remainder is itself an env ref (e.g. ``Bearer ${TOKEN}``),
        # the value is safe.
        if is_env_reference(stripped):
            return
        # Real credentials are dense and contiguous; any remaining whitespace
        # implies prose, not a token.
        if any(ch.isspace() for ch in stripped):
            return
        if (
            len(stripped) >= ENTROPY_MIN_LEN
            and shannon_entropy(stripped) >= ENTROPY_MIN_BITS
        ):
            findings.append(
                Finding(
                    file_path,
                    key_path or parent_key,
                    "auth-looking field has a high-entropy literal; use an env var reference instead",
                )
            )


def lint_mcp_config(file_path: pathlib.Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        findings.append(Finding(file_path, "<file>", f"cannot read file: {exc}"))
        return findings
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        findings.append(Finding(file_path, "<file>", f"invalid JSON: {exc.msg}"))
        return findings
    if not isinstance(data, dict):
        findings.append(
            Finding(file_path, "<root>", "top-level value must be an object")
        )
        return findings
    scan_value(
        file_path=file_path,
        key_path="",
        parent_key="",
        value=data,
        findings=findings,
    )
    return findings


def validate_catalog(file_path: pathlib.Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        findings.append(Finding(file_path, "<file>", f"cannot read file: {exc}"))
        return findings
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        findings.append(Finding(file_path, "<file>", f"invalid JSON: {exc.msg}"))
        return findings
    if not isinstance(data, dict):
        findings.append(
            Finding(file_path, "<root>", "top-level value must be an object")
        )
        return findings
    schema_version = data.get("schema_version")
    if schema_version != 1:
        findings.append(
            Finding(
                file_path,
                "schema_version",
                f"schema_version must be 1 (got {schema_version!r})",
            )
        )
    servers = data.get("servers")
    if not isinstance(servers, dict) or not servers:
        findings.append(
            Finding(file_path, "servers", "servers must be a non-empty object")
        )
        return findings
    for name, entry in servers.items():
        if not isinstance(entry, dict):
            findings.append(
                Finding(
                    file_path, f"servers.{name}", "server entry must be an object"
                )
            )
            continue
        purpose = entry.get("purpose")
        if not isinstance(purpose, str) or not purpose.strip():
            findings.append(
                Finding(
                    file_path,
                    f"servers.{name}.purpose",
                    "purpose must be a non-empty string",
                )
            )
        applies_when = entry.get("applies_when")
        if not isinstance(applies_when, list) or not all(
            isinstance(item, str) and item for item in applies_when
        ):
            findings.append(
                Finding(
                    file_path,
                    f"servers.{name}.applies_when",
                    "applies_when must be a list of non-empty strings",
                )
            )
        if "auth_env" not in entry:
            findings.append(
                Finding(
                    file_path,
                    f"servers.{name}.auth_env",
                    "auth_env must be declared (use null when no credential is required)",
                )
            )
        else:
            auth_env = entry["auth_env"]
            if auth_env is not None:
                if not isinstance(auth_env, str) or not auth_env.strip():
                    findings.append(
                        Finding(
                            file_path,
                            f"servers.{name}.auth_env",
                            "auth_env must be a non-empty string or null",
                        )
                    )
                elif not ENV_VAR_NAME_RE.match(auth_env):
                    # Catch drift: ``auth_env`` is the literal env-var name a
                    # consumer must export, so it has to be a valid POSIX
                    # identifier (e.g. ``GITHUB_TOKEN``), not a placeholder
                    # like ``${GITHUB_TOKEN}`` or a free-form description.
                    findings.append(
                        Finding(
                            file_path,
                            f"servers.{name}.auth_env",
                            "auth_env must be an UPPER_SNAKE environment variable name (matching ^[A-Z_][A-Z0-9_]*$) or null",
                        )
                    )
    return findings


def discover_files(root: pathlib.Path) -> list[tuple[str, pathlib.Path]]:
    """Return ``[(role, path)]`` for every file we should validate."""

    pairs: list[tuple[str, pathlib.Path]] = []
    catalog = root / "core" / "mcp" / "catalog.json"
    if catalog.is_file():
        pairs.append(("catalog", catalog))
    mcp_json = root / ".mcp.json"
    if mcp_json.is_file():
        pairs.append(("config", mcp_json))
    suggested = root / ".mcp.json.suggested"
    if suggested.is_file():
        pairs.append(("suggested", suggested))
    return pairs


def render_report(
    root: pathlib.Path,
    pairs: Iterable[tuple[str, pathlib.Path]],
    findings: Iterable[Finding],
) -> int:
    findings_list = list(findings)
    pair_list = list(pairs)
    if not pair_list:
        print("PASS: no MCP catalog or .mcp.json files present (default bootstrap).")
        return 0
    print("MCP files inspected:")
    for role, path in pair_list:
        try:
            rel = path.relative_to(root)
        except ValueError:
            rel = path
        print(f"  [{role}] {rel}")
    if not findings_list:
        print(f"\nPASS: {len(pair_list)} MCP file(s) passed all checks.")
        return 0
    print("\nFAIL: MCP findings:", file=sys.stderr)
    for finding in findings_list:
        print(finding.render(root), file=sys.stderr)
    print(
        "\nReplace inline secrets with environment variable references "
        "such as ${GITHUB_TOKEN}, then re-run this validator.",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=str(pathlib.Path.cwd()),
        help="Repository root to scan (default: cwd).",
    )
    args = parser.parse_args(argv)
    root = pathlib.Path(args.root).resolve()
    if not root.is_dir():
        print(f"FAIL: --root is not a directory: {root}", file=sys.stderr)
        return 2
    pairs = discover_files(root)
    findings: list[Finding] = []
    for role, path in pairs:
        if role == "catalog":
            findings.extend(validate_catalog(path))
        else:
            findings.extend(lint_mcp_config(path))
    return render_report(root, pairs, findings)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
