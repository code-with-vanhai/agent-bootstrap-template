#!/usr/bin/env python3
"""Append-only JSONL audit log for generated agent systems."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
ALLOWED_KINDS = frozenset({"gate_run", "plan_validation", "subagent_run"})
REQUIRED_PER_KIND = {
    "gate_run": ("gate", "exit_code", "duration_ms"),
    "plan_validation": ("target", "exit_code", "strict"),
    "subagent_run": ("subagent", "outcome"),
}
ALLOWED_TOP_LEVEL_KEYS = frozenset(
    {
        "v",
        "ts",
        "kind",
        "actor",
        "gate",
        "exit_code",
        "duration_ms",
        "target",
        "strict",
        "high",
        "medium",
        "subagent",
        "outcome",
        "notes",
        "extra",
    }
)
OUTCOME_VALUES = frozenset({"complete", "aborted", "error"})
OPT_OUT_SENTINEL = ".agent/audit-log.disabled"
LOG_PATH = ".agent/audit-log.jsonl"
_INT_RE = re.compile(r"^-?[0-9]+$")


class AuditLogError(ValueError):
    """Raised when an audit-log payload is invalid."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_root(root: Path | str | None = None) -> Path:
    if root is not None:
        return Path(root).resolve()

    env_root = os.environ.get("AGENT_ROOT")
    if env_root:
        return Path(env_root).resolve()

    cwd = Path.cwd()
    if (cwd / ".agent").is_dir():
        return cwd.resolve()

    git = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if git.returncode == 0 and git.stdout.strip():
        return Path(git.stdout.strip()).resolve()

    script_root = Path(__file__).resolve().parents[2]
    return script_root


def _coerce_field_value(value: str) -> Any:
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if _INT_RE.fullmatch(value):
        return int(value)
    if value[:1] in {"{", "[", '"'}:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _validate(payload: dict[str, Any]) -> None:
    unknown = sorted(set(payload) - ALLOWED_TOP_LEVEL_KEYS)
    if unknown:
        raise AuditLogError(f"unknown key(s): {', '.join(unknown)}")

    if payload.get("v") != SCHEMA_VERSION:
        raise AuditLogError(f"v must be {SCHEMA_VERSION}")
    ts = payload.get("ts")
    if not isinstance(ts, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", ts):
        raise AuditLogError("ts must be UTC ISO-8601 without fractional seconds")

    kind = payload.get("kind")
    if kind not in ALLOWED_KINDS:
        raise AuditLogError("kind must be one of: " + ", ".join(sorted(ALLOWED_KINDS)))
    if not isinstance(payload.get("actor"), str) or not payload["actor"]:
        raise AuditLogError("actor must be a non-empty string")

    for key in REQUIRED_PER_KIND[str(kind)]:
        if key not in payload:
            raise AuditLogError(f"{kind} missing required key: {key}")

    if kind == "gate_run":
        if not isinstance(payload.get("gate"), str) or not payload["gate"]:
            raise AuditLogError("gate must be a non-empty string")
        if not isinstance(payload.get("exit_code"), int):
            raise AuditLogError("exit_code must be an integer")
        if not isinstance(payload.get("duration_ms"), int) or payload["duration_ms"] < 0:
            raise AuditLogError("duration_ms must be a non-negative integer")
    elif kind == "plan_validation":
        if not isinstance(payload.get("target"), str) or not payload["target"]:
            raise AuditLogError("target must be a non-empty string")
        if not isinstance(payload.get("exit_code"), int):
            raise AuditLogError("exit_code must be an integer")
        if not isinstance(payload.get("strict"), bool):
            raise AuditLogError("strict must be a boolean")
        for optional_count in ("high", "medium"):
            if optional_count in payload and not isinstance(payload[optional_count], int):
                raise AuditLogError(f"{optional_count} must be an integer when present")
    elif kind == "subagent_run":
        if not isinstance(payload.get("subagent"), str) or not payload["subagent"]:
            raise AuditLogError("subagent must be a non-empty string")
        if payload.get("outcome") not in OUTCOME_VALUES:
            raise AuditLogError("outcome must be one of: " + ", ".join(sorted(OUTCOME_VALUES)))

    if "notes" in payload and not isinstance(payload["notes"], str):
        raise AuditLogError("notes must be a string")
    if "extra" in payload and not isinstance(payload["extra"], dict):
        raise AuditLogError("extra must be an object")


def append(payload: dict[str, Any], root: Path | str | None = None, strict: bool = False) -> int:
    record = dict(payload)
    record.setdefault("v", SCHEMA_VERSION)
    record.setdefault("ts", _now_iso())

    try:
        _validate(record)
    except AuditLogError as exc:
        print(f"audit-log: warning: {exc}", file=sys.stderr)
        return 2 if strict else 0

    repo_root = _resolve_root(root)
    agent_dir = repo_root / ".agent"
    if not agent_dir.is_dir():
        return 0
    if (repo_root / OPT_OUT_SENTINEL).exists():
        return 0

    line = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    try:
        fd = os.open(repo_root / LOG_PATH, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
        try:
            os.write(fd, line)
        finally:
            os.close(fd)
    except OSError as exc:
        print(f"audit-log: warning: {exc}", file=sys.stderr)
        return 2 if strict else 0
    return 0


def _parse_field(item: str) -> tuple[str, Any]:
    if "=" not in item:
        raise AuditLogError(f"--field must be key=value, got: {item}")
    key, value = item.split("=", 1)
    if not key:
        raise AuditLogError("--field key must not be empty")
    return key, _coerce_field_value(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")
    append_parser = subparsers.add_parser("append", help="append one audit-log event")
    append_parser.add_argument("--kind", required=True)
    append_parser.add_argument("--actor", required=True)
    append_parser.add_argument("--field", action="append", default=[])
    append_parser.add_argument("--root")
    append_parser.add_argument("--strict", action="store_true")

    args = parser.parse_args(argv)
    if args.command != "append":
        parser.print_usage(sys.stderr)
        return 2

    payload: dict[str, Any] = {"kind": args.kind, "actor": args.actor}
    try:
        for item in args.field:
            key, value = _parse_field(item)
            payload[key] = value
    except AuditLogError as exc:
        print(f"audit-log: warning: {exc}", file=sys.stderr)
        return 2 if args.strict else 0

    return append(payload, root=args.root, strict=args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
