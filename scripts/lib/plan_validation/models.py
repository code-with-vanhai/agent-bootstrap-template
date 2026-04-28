from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple


SEVERITY_HIGH = "High"
SEVERITY_MEDIUM = "Medium"


@dataclass
class Finding:
    check_id: str
    severity: str
    message: str
    file: Optional[Path] = None
    line: Optional[int] = None

    def format_for_human(self) -> str:
        location = ""
        if self.file is not None:
            location = f"{self.file}"
            if self.line is not None:
                location += f":{self.line}"
            location = f" [{location}]"
        return f"  [{self.severity}] {self.check_id}{location}: {self.message}"

    def format_for_github(self) -> str:
        # ::error file=path,line=N::CHECK-ID severity=High message
        kind = "error" if self.severity == SEVERITY_HIGH else "warning"
        attrs = []
        if self.file is not None:
            attrs.append(f"file={self.file}")
        if self.line is not None:
            attrs.append(f"line={self.line}")
        prefix = f"::{kind}"
        if attrs:
            prefix += " " + ",".join(attrs)
        return f"{prefix}::{self.check_id} severity={self.severity} {self.message}"


# ---------------------------------------------------------------------------
# Repo context
# ---------------------------------------------------------------------------


@dataclass
class RepoContext:
    repo_root: Path
    react_version: Optional[str] = None
    is_mv3_extension: bool = False
    detected_signals: List[str] = field(default_factory=list)


@dataclass
class EvidenceBlock:
    start_line: int
    end_line: int
    raw_attrs: str
    path: Optional[str]
    lines: Optional[Tuple[int, int]]
    ref: Optional[str]
    region_sha256: Optional[str]
    snippet: str
    snippet_offset: int  # offset within plan text


@dataclass
class MarkdownTable:
    start_line: int
    rows: List[List[str]]
    row_lines: List[int]


@dataclass
class PlanFile:
    path: Path
    text: str
