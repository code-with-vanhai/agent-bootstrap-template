"""`Check` record + `AgentSystemValidator` class.

The class owns:
  - the result list and the `pass_/fail/skip` recorders,
  - the small assertion helpers (`exists`, `contains`, `json_file`,
    `shell_syntax`, `py_compile`, `manifest_has_feature`),
  - the gate-modes metadata loaded once at construction time,
  - the `run()` orchestrator that delegates to the per-mode check
    modules.

Every check group lives in its own module and takes the validator
instance as its first argument. This keeps the class slim and lets each
concern be edited (and tested) in isolation.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .runtime import read_text, run_subprocess

try:
    from ..gate_modes import (  # type: ignore
        DEFAULT_GATE_MODES,
        GateModesError,
        load_gate_modes_metadata,
    )
except ImportError:  # pragma: no cover - exercised when loaded via shim
    from gate_modes import (  # type: ignore
        DEFAULT_GATE_MODES,
        GateModesError,
        load_gate_modes_metadata,
    )


@dataclass
class Check:
    status: str
    message: str
    path: str | None = None


class AgentSystemValidator:
    def __init__(self, root: Path, mode: str):
        self.root = root
        self.mode = mode
        self.results: list[Check] = []
        self._gate_modes: tuple[str, ...] = DEFAULT_GATE_MODES
        self._gate_metadata: dict[str, object] = {
            "modes": DEFAULT_GATE_MODES,
            "default_gate": "fast",
            "full_gate": "full",
        }
        self._gate_modes_loaded = False
        self._gate_modes_load_error: str | None = None
        try:
            self._gate_metadata = load_gate_modes_metadata(root, mode=mode)
            modes = self._gate_metadata["modes"]
            assert isinstance(modes, tuple)
            self._gate_modes = modes
            self._gate_modes_loaded = True
        except GateModesError as exc:
            self._gate_modes_load_error = str(exc)

    def pass_(self, message: str, path: str | None = None) -> None:
        self.results.append(Check("PASS", message, path))

    def fail(self, message: str, path: str | None = None) -> None:
        self.results.append(Check("FAIL", message, path))

    def skip(self, message: str, path: str | None = None) -> None:
        self.results.append(Check("SKIP", message, path))

    def exists(self, rel: str) -> bool:
        if (self.root / rel).exists():
            self.pass_(f"{rel} exists", rel)
            return True
        self.fail(f"{rel} is missing", rel)
        return False

    def contains(self, rel: str, pattern: str, message: str, regex: bool = False) -> bool:
        path = self.root / rel
        if not path.is_file():
            self.fail(f"{message} cannot be checked because {rel} is missing", rel)
            return False
        text = read_text(path)
        ok = bool(re.search(pattern, text, re.MULTILINE)) if regex else pattern in text
        if ok:
            self.pass_(message, rel)
            return True
        self.fail(message, rel)
        return False

    def json_file(self, rel: str, message: str) -> dict[str, Any] | None:
        path = self.root / rel
        if not path.is_file():
            self.fail(f"{message} cannot be checked because {rel} is missing", rel)
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            self.fail(message, rel)
            return None
        self.pass_(message, rel)
        return data if isinstance(data, dict) else None

    def shell_syntax(self, rel: str) -> None:
        path = self.root / rel
        if not path.is_file():
            self.fail(f"{rel} shell syntax cannot be checked because file is missing", rel)
            return
        result = run_subprocess(["bash", "-n", rel], self.root)
        if result.returncode == 0:
            self.pass_(f"{rel} shell syntax is valid", rel)
        else:
            self.fail(f"{rel} shell syntax is invalid", rel)

    def py_compile(self, paths: Iterable[str], message: str) -> None:
        existing = [path for path in paths if (self.root / path).is_file()]
        if not existing:
            self.fail(f"{message} cannot be checked because no Python files were found")
            return
        result = run_subprocess(
            [sys.executable, "-m", "py_compile", *existing], self.root
        )
        if result.returncode == 0:
            self.pass_(message)
        else:
            self.fail(message)

    def manifest_has_feature(self, data: dict[str, Any] | None, feature: str) -> bool:
        return isinstance(data, dict) and feature in (data.get("features_enabled") or [])

    # ------------------------------------------------------------------
    # Backwards-compatible delegators
    #
    # The single-file 0.10.0 validator exposed the per-concern checks as
    # bound methods on this class. Pre-existing tests (notably
    # ``scripts/lib/test_gate_modes.py``) call those methods directly.
    # The implementations now live as free functions in the per-concern
    # modules; these thin instance methods preserve the public class
    # surface with no behavior change. Imports are deferred to dodge the
    # circular reference (check modules import this class for typing).
    # ------------------------------------------------------------------

    def validate_command_files(self, command_root: str) -> None:
        from .checks_template import validate_command_files

        validate_command_files(self, command_root)

    def validate_gate_modes(self) -> None:
        from .checks_gates import validate_gate_modes

        validate_gate_modes(self)

    def validate_gate_modes_manifest_template(self) -> None:
        from .checks_gates import validate_gate_modes_manifest_template

        validate_gate_modes_manifest_template(self)

    def validate_gate_modes_manifest_generated(self) -> None:
        from .checks_gates import validate_gate_modes_manifest_generated

        validate_gate_modes_manifest_generated(self)

    def validate_gate_candidate_markers_template(self) -> None:
        from .checks_gates import validate_gate_candidate_markers_template

        validate_gate_candidate_markers_template(self)

    def validate_gate_candidate_markers_generated(
        self, manifest: dict[str, Any] | None
    ) -> None:
        from .checks_gates import validate_gate_candidate_markers_generated

        validate_gate_candidate_markers_generated(self, manifest)

    def validate_audit_log_templates(self) -> None:
        from .checks_audit_log import validate_audit_log_templates

        validate_audit_log_templates(self)

    def validate_hook_templates(self) -> None:
        from .checks_hooks import validate_hook_templates

        validate_hook_templates(self)

    def validate_claude_native_subagents(self) -> None:
        from .checks_hooks import validate_claude_native_subagents

        validate_claude_native_subagents(self)

    def validate_thin_adapter_file(self, rel: str) -> None:
        from .checks_adapters import validate_thin_adapter_file_template

        validate_thin_adapter_file_template(self, rel)

    def validate_github_metadata(self, rel: str) -> None:
        from .checks_template import validate_github_metadata

        validate_github_metadata(self, rel)

    def validate_worktree(self, rel: str) -> None:
        from .checks_template import validate_worktree

        validate_worktree(self, rel)

    def validate_constitution_template(self) -> None:
        from .checks_template import validate_constitution_template

        validate_constitution_template(self)

    def validate_constitution_generated(
        self, manifest: dict[str, Any] | None
    ) -> None:
        from .checks_generated import validate_constitution_generated

        validate_constitution_generated(self, manifest)

    def validate_manifest_shape(self, rel: str) -> dict[str, Any] | None:
        from .checks_generated import validate_manifest_shape

        return validate_manifest_shape(self, rel)

    def check_placeholders(self) -> None:
        from .checks_generated import check_placeholders

        check_placeholders(self)

    def load_skill_manifest(self) -> list[str]:
        from .checks_skills import load_skill_manifest

        return load_skill_manifest(self)

    def validate_skill_set(self, skills: list[str]) -> None:
        from .checks_skills import validate_skill_set

        validate_skill_set(self, skills)

    def validate_skill_mapping(self, skills: list[str]) -> None:
        from .checks_skills import validate_skill_mapping

        validate_skill_mapping(self, skills)

    def validate_skill_count_docs(self, skills: list[str]) -> None:
        from .checks_skills import validate_skill_count_docs

        validate_skill_count_docs(self, skills)

    def validate_template(self) -> None:
        from .checks_template import validate_template

        validate_template(self)

    def validate_generated(self) -> None:
        from .checks_generated import validate_generated

        validate_generated(self)

    def validate_token_budget(self) -> None:
        from .token_budget import validate_token_budget

        validate_token_budget(self)

    def run(self) -> list[Check]:
        if self.mode == "template":
            self.validate_template()
        else:
            self.validate_generated()
        self.validate_token_budget()
        return self.results
