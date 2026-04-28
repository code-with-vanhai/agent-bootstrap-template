#!/usr/bin/env python3
"""Render Agent Bootstrap template placeholders.

This module intentionally uses literal string replacement for known
``{{TOKEN}}`` placeholders. Replacement values are data, not sed or regex
program fragments, so backslashes, ampersands, quotes, and newlines are kept
verbatim.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Mapping


PLACEHOLDER_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")


def render_text(text: str, tokens: Mapping[str, object], fallback: str) -> str:
    rendered = text
    for token, value in tokens.items():
        rendered = rendered.replace("{{" + token + "}}", str(value))
    return PLACEHOLDER_RE.sub(fallback, rendered)


def render_file(path: Path, tokens: Mapping[str, object], fallback: str) -> None:
    text = path.read_text(encoding="utf-8")
    path.write_text(render_text(text, tokens, fallback), encoding="utf-8")


def load_tokens(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"token map must be a JSON object: {path}")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Render {{TOKEN}} placeholders in a file.")
    parser.add_argument("file", type=Path)
    parser.add_argument("tokens_json", type=Path)
    parser.add_argument(
        "--fallback",
        default="not confirmed - complete .agent/bootstrap-pending.md",
        help="replacement for unknown all-caps placeholders",
    )
    args = parser.parse_args()

    render_file(args.file, load_tokens(args.tokens_json), args.fallback)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
