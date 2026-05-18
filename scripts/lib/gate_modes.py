#!/usr/bin/env python3
"""Authoritative gate-mode loader.

Centralizes the list of valid gate modes so checked-in consumers
(`validate_agent_system.py`, `insert_gate_candidates.py`, generated
`scripts/agent-eval.sh`) cannot drift independently.

Two execution contexts:

- Template mode (running inside the agent-bootstrap-template repo):
  `core/gate-modes.json` is required. Its absence or schema mismatch is a
  hard failure so a gate-mode change cannot silently update only one
  consumer.
- Generated mode (running inside a downstream bootstrapped repo): a future
  `.agent/gate-modes.json` will be honored if present, otherwise we fall
  back to `DEFAULT_GATE_MODES` so 0.9.0-era generated repos keep working
  until they are migrated.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Tuple

DEFAULT_GATE_MODES: Tuple[str, ...] = (
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

DEFAULT_GATE: str = "fast"
FULL_GATE: str = "full"

TEMPLATE_PATH = "core/gate-modes.json"
GENERATED_PATH = ".agent/gate-modes.json"
SUPPORTED_SCHEMA_VERSIONS = frozenset({1, 2})


class GateModesError(RuntimeError):
    """Raised when a gate-modes manifest exists but is malformed."""


def _validate_composite_gates(
    data: Mapping[str, Any], *, modes: Tuple[str, ...], source: Path
) -> dict[str, Any] | None:
    schema_version = data.get("schema_version")
    composite_gates = data.get("composite_gates")
    if schema_version == 1:
        if composite_gates is not None:
            raise GateModesError(
                f"{source}: 'composite_gates' requires schema_version 2"
            )
        return None

    if composite_gates is None:
        return None
    if not isinstance(composite_gates, dict):
        raise GateModesError(f"{source}: 'composite_gates' must be an object")

    mode_set = set(modes)
    composite_names = set(composite_gates)
    for gate_name, definition in composite_gates.items():
        if not isinstance(gate_name, str) or gate_name not in mode_set:
            raise GateModesError(
                f"{source}: composite gate {gate_name!r} must be present in 'modes'"
            )
        if not isinstance(definition, dict):
            raise GateModesError(
                f"{source}: composite gate {gate_name!r} must be an object"
            )
        unknown = sorted(set(definition) - {"stages"})
        if unknown:
            raise GateModesError(
                f"{source}: composite gate {gate_name!r} has unknown key(s): "
                + ", ".join(unknown)
            )
        stages = definition.get("stages")
        if not isinstance(stages, list) or not stages:
            raise GateModesError(
                f"{source}: composite gate {gate_name!r} must define non-empty stages"
            )
        for index, stage in enumerate(stages, start=1):
            if not isinstance(stage, dict):
                raise GateModesError(
                    f"{source}: composite gate {gate_name!r} stage {index} "
                    "must be an object"
                )
            unknown_stage_keys = sorted(set(stage) - {"parallel", "serial"})
            if unknown_stage_keys:
                raise GateModesError(
                    f"{source}: composite gate {gate_name!r} stage {index} "
                    "has unknown key(s): "
                    + ", ".join(unknown_stage_keys)
                )
            if "parallel" not in stage and "serial" not in stage:
                raise GateModesError(
                    f"{source}: composite gate {gate_name!r} stage {index} "
                    "must define 'parallel' or 'serial'"
                )
            for key in ("parallel", "serial"):
                if key not in stage:
                    continue
                values = stage[key]
                if not isinstance(values, list) or not values:
                    raise GateModesError(
                        f"{source}: composite gate {gate_name!r} stage {index} "
                        f"'{key}' must be a non-empty list"
                    )
                if not all(isinstance(item, str) for item in values):
                    raise GateModesError(
                        f"{source}: composite gate {gate_name!r} stage {index} "
                        f"'{key}' entries must be strings"
                    )
                for referenced in values:
                    if referenced not in mode_set:
                        raise GateModesError(
                            f"{source}: composite gate {gate_name!r} references "
                            f"unknown mode {referenced!r}"
                        )
                    if referenced == gate_name:
                        raise GateModesError(
                            f"{source}: composite gate {gate_name!r} references itself"
                        )
                    if referenced in composite_names:
                        raise GateModesError(
                            f"{source}: composite gate {gate_name!r} references "
                            f"composite gate {referenced!r}"
                        )
    return dict(composite_gates)


def _validate_payload(data: object, *, source: Path) -> Tuple[str, ...]:
    if not isinstance(data, dict):
        raise GateModesError(f"{source}: top-level value must be a JSON object")
    if data.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
        raise GateModesError(
            f"{source}: unsupported schema_version (expected 1 or 2, got "
            f"{data.get('schema_version')!r})"
        )
    modes = data.get("modes")
    if not isinstance(modes, list) or not modes:
        raise GateModesError(f"{source}: 'modes' must be a non-empty list of strings")
    if not all(isinstance(item, str) for item in modes):
        raise GateModesError(f"{source}: every entry in 'modes' must be a string")
    if len(set(modes)) != len(modes):
        raise GateModesError(f"{source}: 'modes' contains duplicate entries")

    default_gate = data.get("default_gate")
    full_gate = data.get("full_gate")
    if not isinstance(default_gate, str) or default_gate not in modes:
        raise GateModesError(
            f"{source}: 'default_gate' must be a string present in 'modes'"
        )
    if not isinstance(full_gate, str) or full_gate not in modes:
        raise GateModesError(
            f"{source}: 'full_gate' must be a string present in 'modes'"
        )
    modes_tuple = tuple(modes)
    _validate_composite_gates(data, modes=modes_tuple, source=source)
    return modes_tuple


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def load_gate_modes(root: Path, *, mode: str) -> Tuple[str, ...]:
    """Return the authoritative gate-mode tuple for a given root.

    Args:
        root: repo root (template root or generated repo root).
        mode: ``"template"`` requires `core/gate-modes.json`; ``"generated"``
            falls back to ``DEFAULT_GATE_MODES`` when the manifest is
            absent.
    """

    if mode == "template":
        manifest = root / TEMPLATE_PATH
        if not manifest.is_file():
            raise GateModesError(
                f"{TEMPLATE_PATH} is required in template mode but not found"
            )
        return _validate_payload(_read_json(manifest), source=manifest)

    if mode == "generated":
        manifest = root / GENERATED_PATH
        if manifest.is_file():
            return _validate_payload(_read_json(manifest), source=manifest)
        return DEFAULT_GATE_MODES

    raise ValueError(f"unknown mode: {mode!r}")


def load_gate_modes_metadata(root: Path, *, mode: str) -> dict[str, object]:
    """Return the full validated payload (modes, default_gate, full_gate)."""

    if mode == "template":
        manifest = root / TEMPLATE_PATH
        if not manifest.is_file():
            raise GateModesError(
                f"{TEMPLATE_PATH} is required in template mode but not found"
            )
        data = _read_json(manifest)
        modes = _validate_payload(data, source=manifest)
        assert isinstance(data, dict)
        return {
            "modes": modes,
            "default_gate": data["default_gate"],
            "full_gate": data["full_gate"],
            "composite_gates": _validate_composite_gates(
                data, modes=modes, source=manifest
            ),
        }

    if mode == "generated":
        manifest = root / GENERATED_PATH
        if manifest.is_file():
            data = _read_json(manifest)
            modes = _validate_payload(data, source=manifest)
            assert isinstance(data, dict)
            return {
                "modes": modes,
                "default_gate": data["default_gate"],
                "full_gate": data["full_gate"],
                "composite_gates": _validate_composite_gates(
                    data, modes=modes, source=manifest
                ),
            }
        return {
            "modes": DEFAULT_GATE_MODES,
            "default_gate": DEFAULT_GATE,
            "full_gate": FULL_GATE,
            "composite_gates": None,
        }

    raise ValueError(f"unknown mode: {mode!r}")


def load_composite_gates(root: Path, *, mode: str) -> dict[str, Any] | None:
    """Return the optional schema-v2 composite gate block for a root."""

    metadata = load_gate_modes_metadata(root, mode=mode)
    composite_gates = metadata.get("composite_gates")
    if composite_gates is None:
        return None
    assert isinstance(composite_gates, dict)
    return composite_gates
