#!/usr/bin/env python3
"""Run schema-v2 composite gates from gate-modes.json."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    from . import audit_log
    from .gate_modes import GateModesError
except ImportError:
    import audit_log  # type: ignore
    from gate_modes import GateModesError  # type: ignore


_live_children: set[subprocess.Popen[bytes]] = set()
_live_children_lock = threading.Lock()


@dataclass(frozen=True)
class CompositeGate:
    name: str
    stages: tuple[dict[str, tuple[str, ...]], ...]


@dataclass(frozen=True)
class SubGateResult:
    gate: str
    exit_code: int
    duration_ms: int
    stdout_path: Path
    stderr_path: Path

    def audit_payload(self) -> dict[str, int | str]:
        return {
            "gate": self.gate,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
        }


def _read_gate_modes(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "schema_version": 2,
            "modes": [],
            "default_gate": "",
            "full_gate": "",
            "composite_gates": {},
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise GateModesError(f"{path}: top-level value must be a JSON object")
    return data


def load_composite(gate_name: str, gate_modes_path: str | Path) -> CompositeGate | None:
    data = _read_gate_modes(Path(gate_modes_path))
    raw_composites = data.get("composite_gates")
    if not isinstance(raw_composites, dict) or gate_name not in raw_composites:
        return None
    raw_composite = raw_composites[gate_name]
    if not isinstance(raw_composite, dict):
        raise GateModesError(f"{gate_modes_path}: composite gate {gate_name!r} invalid")
    raw_stages = raw_composite.get("stages")
    if not isinstance(raw_stages, list) or not raw_stages:
        raise GateModesError(
            f"{gate_modes_path}: composite gate {gate_name!r} must define stages"
        )
    stages: list[dict[str, tuple[str, ...]]] = []
    for raw_stage in raw_stages:
        if not isinstance(raw_stage, dict):
            raise GateModesError(
                f"{gate_modes_path}: composite gate {gate_name!r} stage invalid"
            )
        stage: dict[str, tuple[str, ...]] = {}
        for key in ("serial", "parallel"):
            if key not in raw_stage:
                continue
            values = raw_stage[key]
            if not isinstance(values, list) or not all(
                isinstance(item, str) for item in values
            ):
                raise GateModesError(
                    f"{gate_modes_path}: composite gate {gate_name!r} "
                    f"stage {key!r} must be a string list"
                )
            stage[key] = tuple(values)
        stages.append(stage)
    return CompositeGate(gate_name, tuple(stages))


def _register_child(proc: subprocess.Popen[bytes]) -> None:
    with _live_children_lock:
        _live_children.add(proc)


def _unregister_child(proc: subprocess.Popen[bytes]) -> None:
    with _live_children_lock:
        _live_children.discard(proc)


def terminate_live_children() -> None:
    with _live_children_lock:
        children = list(_live_children)
    for proc in children:
        if proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass
    for proc in children:
        if proc.poll() is None:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except OSError:
                    pass


def _handle_signal(signum: int, _frame: object) -> None:
    terminate_live_children()
    raise SystemExit(128 + signum)


def install_signal_handlers() -> None:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)


def _run_child(gate: str, eval_script_path: Path, root: Path) -> SubGateResult:
    stdout_file = tempfile.NamedTemporaryFile(prefix=f"gate-{gate}-", delete=False)
    stderr_file = tempfile.NamedTemporaryFile(prefix=f"gate-{gate}-", delete=False)
    stdout_path = Path(stdout_file.name)
    stderr_path = Path(stderr_file.name)
    start = time.time()
    proc: subprocess.Popen[bytes] | None = None
    try:
        env = dict(os.environ)
        env["AGENT_EVAL_SUPPRESS_AUDIT"] = "1"
        proc = subprocess.Popen(
            ["bash", str(eval_script_path), gate],
            cwd=str(root),
            env=env,
            stdout=stdout_file,
            stderr=stderr_file,
        )
        _register_child(proc)
        exit_code = proc.wait()
    finally:
        if proc is not None:
            _unregister_child(proc)
        stdout_file.close()
        stderr_file.close()
    duration_ms = int(max(0, (time.time() - start) * 1000))
    return SubGateResult(gate, int(exit_code), duration_ms, stdout_path, stderr_path)


def _replay_outputs(results: Iterable[SubGateResult]) -> None:
    for result in results:
        try:
            sys.stdout.write(result.stdout_path.read_text(encoding="utf-8", errors="replace"))
        finally:
            try:
                result.stdout_path.unlink()
            except OSError:
                pass
        try:
            sys.stderr.write(result.stderr_path.read_text(encoding="utf-8", errors="replace"))
        finally:
            try:
                result.stderr_path.unlink()
            except OSError:
                pass


def run_stage(
    stage: dict[str, tuple[str, ...]], eval_script_path: str | Path, root: str | Path
) -> list[SubGateResult]:
    eval_path = Path(eval_script_path)
    repo_root = Path(root)
    results: list[SubGateResult] = []
    for gate in stage.get("serial", ()):
        results.append(_run_child(gate, eval_path, repo_root))
    parallel = stage.get("parallel", ())
    if parallel:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(parallel)) as pool:
            futures = [
                pool.submit(_run_child, gate, eval_path, repo_root)
                for gate in parallel
            ]
            for future in futures:
                results.append(future.result())
    _replay_outputs(results)
    return results


def aggregate_exit_codes(results: Iterable[SubGateResult | int]) -> int:
    codes = [
        item.exit_code if isinstance(item, SubGateResult) else int(item)
        for item in results
    ]
    if not codes:
        return 0
    if all(code == 2 for code in codes):
        return 2
    non_not_configured = [code for code in codes if code != 2]
    return max(non_not_configured) if non_not_configured else 2


def emit_composite_audit(
    gate: str, exit_code: int, duration_ms: int, results: list[SubGateResult], root: Path
) -> None:
    audit_log.append(
        {
            "kind": "gate_run",
            "actor": "scripts/lib/gate_runner.py",
            "gate": gate,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "sub_gates": [result.audit_payload() for result in results],
        },
        root=root,
    )


def run_composite(
    composite: CompositeGate, eval_script_path: str | Path, root: str | Path
) -> int:
    repo_root = Path(root)
    start = time.time()
    all_results: list[SubGateResult] = []
    for stage in composite.stages:
        all_results.extend(run_stage(stage, eval_script_path, repo_root))
    exit_code = aggregate_exit_codes(all_results)
    duration_ms = int(max(0, (time.time() - start) * 1000))
    emit_composite_audit(composite.name, exit_code, duration_ms, all_results, repo_root)
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")

    is_parser = subparsers.add_parser("is-composite")
    is_parser.add_argument("--gate", required=True)
    is_parser.add_argument("--gate-modes", required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--gate", required=True)
    run_parser.add_argument("--gate-modes", required=True)
    run_parser.add_argument("--eval-script", required=True)
    run_parser.add_argument("--root", required=True)

    args = parser.parse_args(argv)
    if args.command == "is-composite":
        composite = load_composite(args.gate, args.gate_modes)
        print("yes" if composite is not None else "no")
        return 0
    if args.command == "run":
        install_signal_handlers()
        composite = load_composite(args.gate, args.gate_modes)
        if composite is None:
            print(f"gate is not composite: {args.gate}", file=sys.stderr)
            return 2
        return run_composite(composite, args.eval_script, args.root)
    parser.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
