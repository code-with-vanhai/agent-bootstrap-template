#!/usr/bin/env python3
"""Insert candidate gate commands into a generated scripts/agent-eval.sh.

Reads `<target>/scripts/agent-eval.sh`, runs `gate_discovery.discover` against
`<target>` (or an explicit `--root`), and replaces the body between each gate's
AGENT-CANDIDATES marker pair with one commented stub per discovered candidate.
The result is idempotent: re-running on an already-populated file produces
byte-identical output. Promotion of a stub remains a deliberate human edit;
this script only writes commented (`#`) lines.

The expected marker pair for each gate is:

    # >>> AGENT-CANDIDATES gate=<name> — review before promoting <<<
    # <<< END AGENT-CANDIDATES gate=<name> <<<

If either marker is missing for any gate listed in EXPECTED_GATE_MODES, the
script aborts with `SystemExit(2)` so the caller can re-bootstrap with
`--force --discover-gates` to restore them.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

try:
    from .gate_discovery import Candidate, discover
except ImportError:
    from gate_discovery import Candidate, discover  # type: ignore  # noqa: F401

EXPECTED_GATE_MODES = (
    "changed",
    "fast",
    "frontend",
    "backend",
    "shared",
    "e2e",
    "full",
    "security",
    "release",
)


def marker_open(gate: str) -> str:
    return f"# >>> AGENT-CANDIDATES gate={gate} — review before promoting <<<"


def marker_close(gate: str) -> str:
    return f"# <<< END AGENT-CANDIDATES gate={gate} <<<"


def _detect_indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" "))]


def _render_candidate_lines(indent: str, candidates: Iterable[Candidate]) -> list[str]:
    lines: list[str] = []
    for cand in candidates:
        source = f"{cand.evidence_file}::{cand.evidence_key}"
        lines.append(
            f"{indent}#   run {cand.command}           "
            f"# source: {source} (confidence={cand.confidence})"
        )
    return lines


def _replace_block(
    text: str,
    *,
    open_marker: str,
    close_marker: str,
    new_body: list[str],
    gate: str,
) -> str:
    lines = text.splitlines(keepends=False)
    open_idx = next(
        (i for i, ln in enumerate(lines) if ln.lstrip(" ") == open_marker.lstrip(" ")),
        None,
    )
    close_idx = next(
        (i for i, ln in enumerate(lines) if ln.lstrip(" ") == close_marker.lstrip(" ")),
        None,
    )
    if open_idx is None:
        raise SystemExit(
            f"insert_gate_candidates: missing open marker for gate={gate}: "
            f"expected `{open_marker}` in scripts/agent-eval.sh"
        )
    if close_idx is None or close_idx <= open_idx:
        raise SystemExit(
            f"insert_gate_candidates: missing or misplaced close marker for "
            f"gate={gate}: expected `{close_marker}` after the open marker"
        )
    new_lines = lines[: open_idx + 1] + new_body + lines[close_idx:]
    trailing_newline = "\n" if text.endswith("\n") else ""
    return "\n".join(new_lines) + trailing_newline


def insert(target: Path, *, root: Path | None = None) -> dict[str, int]:
    """Populate AGENT-CANDIDATES blocks in target/scripts/agent-eval.sh.

    Returns a mapping of gate name to candidate count (0 if no candidates were
    discovered for that gate).
    """

    eval_path = target / "scripts" / "agent-eval.sh"
    if not eval_path.is_file():
        raise SystemExit(
            f"insert_gate_candidates: {eval_path} not found; run bootstrap first"
        )

    discovery_root = (root or target).resolve()
    candidates = discover(discovery_root)
    by_gate: dict[str, list[Candidate]] = {gate: [] for gate in EXPECTED_GATE_MODES}
    for cand in candidates:
        by_gate.setdefault(cand.gate, []).append(cand)

    text = eval_path.read_text(encoding="utf-8")
    counts: dict[str, int] = {}
    for gate in EXPECTED_GATE_MODES:
        open_m = marker_open(gate)
        close_m = marker_close(gate)
        original_lines = text.splitlines(keepends=False)
        open_idx = next(
            (i for i, ln in enumerate(original_lines) if ln.lstrip(" ") == open_m.lstrip(" ")),
            None,
        )
        if open_idx is None:
            raise SystemExit(
                f"insert_gate_candidates: missing open marker for gate={gate}: "
                f"expected `{open_m}` in scripts/agent-eval.sh"
            )
        indent = _detect_indent(original_lines[open_idx])
        body = _render_candidate_lines(indent, by_gate.get(gate, ()))
        text = _replace_block(
            text,
            open_marker=open_m,
            close_marker=close_m,
            new_body=body,
            gate=gate,
        )
        counts[gate] = len(body)

    eval_path.write_text(text, encoding="utf-8")
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="Bootstrapped target repo")
    parser.add_argument(
        "--root",
        default=None,
        help="Repository root used for gate_discovery (defaults to --target)",
    )
    args = parser.parse_args(argv)

    target = Path(args.target).resolve()
    root = Path(args.root).resolve() if args.root else None
    counts = insert(target, root=root)

    populated = [(gate, count) for gate, count in counts.items() if count]
    if not populated:
        print(
            "insert_gate_candidates: no candidates discovered; markers preserved "
            "with empty bodies."
        )
        return 0

    print("insert_gate_candidates: populated gates:")
    for gate, count in populated:
        print(f"  - {gate}: {count} candidate(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
