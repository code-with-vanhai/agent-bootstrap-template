"""Gate-mode and gate-candidate-marker checks.

Covers the three places gate-mode drift can hide:

  - the per-mode files in template/generated layouts (manifest, eval
    template, verify command, schema enum),
  - the AGENT-CANDIDATES marker pairs surrounding insertable command
    stubs, and
  - the `.agent/manifest.json` / `core/manifest.template.json` shape
    around gate modes.
"""

from __future__ import annotations

import re
from typing import Any

from .constants import (
    GATE_CANDIDATE_MARKER_CLOSE_FMT,
    GATE_CANDIDATE_MARKER_OPEN_FMT,
    GATE_CANDIDATE_RUN_RE,
)
from .core import AgentSystemValidator
from .runtime import read_text


def validate_gate_modes(validator: AgentSystemValidator) -> None:
    for mode in validator._gate_modes:
        validator.contains(
            "core/manifest.template.json",
            f'"{mode}"',
            f"core/manifest.template.json includes {mode} gate mode",
        )
        validator.contains(
            "core/commands/verify.md",
            f"`{mode}`",
            f"core/commands/verify.md includes {mode} gate mode",
        )
        validator.contains(
            "scripts/agent-eval.template.sh",
            f"{mode})",
            f"scripts/agent-eval.template.sh includes {mode} gate mode",
        )


def validate_gate_modes_manifest_template(validator: AgentSystemValidator) -> None:
    rel = "core/gate-modes.json"
    if validator._gate_modes_load_error is not None:
        validator.fail(
            f"{rel} load failed: {validator._gate_modes_load_error}",
            rel,
        )
        return
    if not validator._gate_modes_loaded:
        validator.fail(
            f"{rel} is required in template mode but was not loaded",
            rel,
        )
        return
    validator.pass_(
        f"{rel} loaded {len(validator._gate_modes)} gate modes",
        rel,
    )

    schema_rel = "core/manifest.schema.json"
    schema_data = validator.json_file(schema_rel, f"{schema_rel} is valid JSON")
    if isinstance(schema_data, dict):
        verification_props = (
            schema_data.get("properties", {})
            .get("verification", {})
            .get("properties", {})
        )
        enum = (
            verification_props.get("gate_modes", {})
            .get("items", {})
            .get("enum")
        )
        if isinstance(enum, list) and tuple(enum) == validator._gate_modes:
            validator.pass_(
                f"{schema_rel} verification.gate_modes enum matches "
                f"core/gate-modes.json",
                schema_rel,
            )
        else:
            validator.fail(
                f"{schema_rel} verification.gate_modes enum drift; "
                f"expected {list(validator._gate_modes)} from core/gate-modes.json, "
                f"got {enum!r}",
                schema_rel,
            )

    manifest_rel = "core/manifest.template.json"
    manifest_path = validator.root / manifest_rel
    if manifest_path.is_file():
        text = read_text(manifest_path)
        # The template contains TEMPLATE_VERSION-style placeholders so
        # we cannot json.loads it. Extract the gate_modes array as text
        # and compare entries to core/gate-modes.json.
        gate_match = re.search(
            r'"gate_modes"\s*:\s*\[(.*?)\]', text, re.DOTALL
        )
        if not gate_match:
            validator.fail(
                f"{manifest_rel} missing verification.gate_modes array",
                manifest_rel,
            )
        else:
            listed = tuple(re.findall(r'"([^"]+)"', gate_match.group(1)))
            if listed == validator._gate_modes:
                validator.pass_(
                    f"{manifest_rel} verification.gate_modes matches "
                    f"core/gate-modes.json",
                    manifest_rel,
                )
            else:
                validator.fail(
                    f"{manifest_rel} verification.gate_modes drift; "
                    f"expected {list(validator._gate_modes)} from core/gate-modes.json, "
                    f"got {list(listed)}",
                    manifest_rel,
                )


def validate_gate_modes_manifest_generated(validator: AgentSystemValidator) -> None:
    """Generated mode: file absent is fine (fallback). Present-but-malformed
    must FAIL — the loader caught the parse/schema error in __init__ and
    stashed the message in _gate_modes_load_error.
    """

    rel = ".agent/gate-modes.json"
    path = validator.root / rel
    if not path.is_file():
        validator.skip(
            f"{rel} not present; using DEFAULT_GATE_MODES fallback",
            rel,
        )
        return
    if validator._gate_modes_load_error is not None:
        validator.fail(
            f"{rel} present but invalid: {validator._gate_modes_load_error}",
            rel,
        )
        return
    validator.pass_(
        f"{rel} loaded {len(validator._gate_modes)} gate modes",
        rel,
    )


def validate_gate_candidate_markers_template(validator: AgentSystemValidator) -> None:
    rel = "scripts/agent-eval.template.sh"
    if not (validator.root / rel).is_file():
        validator.fail(f"{rel} is missing", rel)
        return
    text = read_text(validator.root / rel)
    for gate in validator._gate_modes:
        open_marker = GATE_CANDIDATE_MARKER_OPEN_FMT.format(gate=gate)
        close_marker = GATE_CANDIDATE_MARKER_CLOSE_FMT.format(gate=gate)
        if open_marker in text and close_marker in text:
            validator.pass_(
                f"{rel} includes AGENT-CANDIDATES marker pair for gate={gate}", rel
            )
        else:
            missing = "open" if open_marker not in text else "close"
            validator.fail(
                f"{rel} missing AGENT-CANDIDATES {missing} marker for gate={gate}",
                rel,
            )


def validate_gate_candidate_markers_generated(
    validator: AgentSystemValidator, manifest: dict[str, Any] | None
) -> None:
    rel = "scripts/agent-eval.sh"
    path = validator.root / rel
    if not path.is_file():
        validator.skip(f"{rel} missing; gate-candidate marker checks skipped", rel)
        return
    text = read_text(path)
    all_markers_present = True
    gate_segments: dict[str, str] = {}
    for gate in validator._gate_modes:
        open_marker = GATE_CANDIDATE_MARKER_OPEN_FMT.format(gate=gate)
        close_marker = GATE_CANDIDATE_MARKER_CLOSE_FMT.format(gate=gate)
        try:
            start = text.index(open_marker)
            end = text.index(close_marker, start + len(open_marker))
        except ValueError:
            missing = "open" if open_marker not in text else "close"
            validator.fail(
                f"{rel} missing AGENT-CANDIDATES {missing} marker for gate={gate}",
                rel,
            )
            all_markers_present = False
            continue
        gate_segments[gate] = text[start + len(open_marker) : end]
        validator.pass_(
            f"{rel} includes AGENT-CANDIDATES marker pair for gate={gate}", rel
        )

    if not all_markers_present:
        return

    if validator.manifest_has_feature(manifest, "gate-candidate-discovery"):
        populated = [
            gate
            for gate, segment in gate_segments.items()
            if GATE_CANDIDATE_RUN_RE.search(segment)
        ]
        if populated:
            validator.pass_(
                f"{rel} contains discovered candidate stubs for gates: "
                f"{', '.join(populated)}",
                rel,
            )
        else:
            validator.fail(
                f"{rel} declares gate-candidate-discovery feature but no "
                "AGENT-CANDIDATES block contains a `#   run ` stub",
                rel,
            )
    else:
        validator.skip(
            f"{rel} gate-candidate-discovery feature not declared; stub population not required",
            rel,
        )
