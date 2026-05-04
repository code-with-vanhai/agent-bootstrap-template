"""Anchor-based ``patches`` planner.

Each ``patches[]`` item in a migration JSON describes an insertion
keyed on a string anchor that must occur exactly once in the target
file (otherwise the patch refuses to apply, to keep the change
deterministic).

If ``require_bash_syntax_ok_after`` is set, the patched bytes are
written to a tmp file and run through ``bash -n`` before being
committed to the planner's ``writes`` dict — this is how the
0.5.0/0.6.0/... shell-script patches stay safe across ``sh``
implementations.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile

from .errors import ConflictError
from .io_utils import read_bytes, rel_path


def plan_patches(target, migration, writes, updated):
    for patch in migration.get("patches", []):
        target_rel = rel_path(patch["file"])
        current = writes.get(target_rel)
        if current is None:
            current = read_bytes(target / target_rel)
        if current is None:
            raise ConflictError(f"patch target is missing: {target_rel}")
        text = current.decode("utf-8")

        skip = patch.get("skip_if_contains")
        if skip and skip in text:
            continue

        anchor = patch["anchor"]
        matches = [match.start() for match in re.finditer(re.escape(anchor), text)]
        if len(matches) != 1:
            raise ConflictError(
                f"patch anchor for {target_rel} matched {len(matches)} times; expected exactly 1"
            )

        line_end = text.find("\n", matches[0])
        if line_end == -1:
            line_end = len(text)
            insert_at = line_end
            separator = "\n"
        else:
            insert_at = line_end + 1
            separator = ""
        patched = (
            text[:insert_at]
            + separator
            + patch["insert_after_first_match"]
            + text[insert_at:]
        )

        if patch.get("require_bash_syntax_ok_after"):
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", delete=False
            ) as fh:
                fh.write(patched)
                temp_name = fh.name
            try:
                result = subprocess.run(
                    ["bash", "-n", temp_name],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                if result.returncode != 0:
                    raise ConflictError(
                        f"patched {target_rel} failed bash -n: {result.stderr.strip()}"
                    )
            finally:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass

        writes[target_rel] = patched.encode("utf-8")
        updated.append(f"{target_rel} patched")
