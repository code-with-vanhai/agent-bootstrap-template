#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

# Derive expected fast-eval list from scripts/agent-evals.sh by parsing the
# deterministic_evals=( ... ) block as text. We deliberately do NOT source
# the runner: sourcing would execute its normal setup (provider resolution,
# artifact-dir handling) which is too risky for a unit-style shell test.
expected_list_file="$(mktemp /tmp/agent-evals-expected.XXXXXX)"
python3 - "$ROOT/scripts/agent-evals.sh" "$expected_list_file" <<'PY'
import re
import sys

source_path = sys.argv[1]
out_path = sys.argv[2]
with open(source_path, "r", encoding="utf-8") as fh:
    text = fh.read()

match = re.search(r"deterministic_evals=\(\s*(.*?)\s*\)", text, flags=re.DOTALL)
if not match:
    raise SystemExit("could not find deterministic_evals=( ... ) block")

entries = []
for raw in match.group(1).splitlines():
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    item = line.strip().strip('"').strip("'")
    if item.startswith("tests/evals/") and item.endswith(".sh"):
        entries.append(item)

if not entries:
    raise SystemExit("deterministic_evals block did not yield any tests/evals/*.sh entries")

with open(out_path, "w", encoding="utf-8") as fh:
    for entry in entries:
        fh.write(entry + "\n")
PY

expected_count="$(wc -l < "$expected_list_file" | tr -d '[:space:]')"

# Mirrors artifact_safe_name() in scripts/agent-evals.sh.
artifact_safe_name() {
  printf '%s' "$1" | tr '/ ' '__' | tr -c 'A-Za-z0-9_.-' '_'
}

artifact_dir="$(mktemp -d /tmp/agent-evals-artifacts.XXXXXX)"
env_artifact_dir="$(mktemp -d /tmp/agent-evals-env-artifacts.XXXXXX)"
cli_artifact_dir="$(mktemp -d /tmp/agent-evals-cli-artifacts.XXXXXX)"
cleanup() {
  rm -rf "$artifact_dir" "$env_artifact_dir" "$cli_artifact_dir" "$expected_list_file"
}
trap cleanup EXIT

scripts/agent-evals.sh --fast --artifact-dir "$artifact_dir" >/tmp/agent-evals-artifacts.out

# Single discovery strategy: depth-1 glob of metadata.json. The runner writes
# exactly one artifact directory per eval. We use Python's pathlib.glob rather
# than `find -maxdepth/-mindepth` because BSD/macOS find historically lacked
# those flags; the simpler `find -name metadata.json` on a fresh artifact dir
# also works but loses the depth-1 invariant we want to assert.
metadata_count="$(python3 -c '
import pathlib, sys
print(len(list(pathlib.Path(sys.argv[1]).glob("*/metadata.json"))))
' "$artifact_dir")"
if [ "$metadata_count" -ne "$expected_count" ]; then
  printf 'FAIL: expected %s metadata files (from deterministic_evals), got %s\n' "$expected_count" "$metadata_count" >&2
  python3 -c '
import pathlib, sys
for p in sorted(pathlib.Path(sys.argv[1]).rglob("*")):
    if p.is_file():
        print(p)
' "$artifact_dir" >&2
  exit 1
fi

# Each expected eval must have exactly one artifact dir with metadata.json
# AND output.txt. Use the artifact-safe naming rule from the runner.
while IFS= read -r eval_script; do
  [ -n "$eval_script" ] || continue
  safe="$(artifact_safe_name "$eval_script")"
  eval_artifact_dir="$artifact_dir/$safe"
  if [ ! -d "$eval_artifact_dir" ]; then
    printf 'FAIL: missing artifact dir for %s (expected %s)\n' "$eval_script" "$eval_artifact_dir" >&2
    exit 1
  fi
  if [ ! -f "$eval_artifact_dir/metadata.json" ]; then
    printf 'FAIL: missing metadata.json under %s\n' "$eval_artifact_dir" >&2
    exit 1
  fi
  if [ ! -f "$eval_artifact_dir/output.txt" ]; then
    printf 'FAIL: missing output.txt under %s\n' "$eval_artifact_dir" >&2
    exit 1
  fi
done < "$expected_list_file"

python3 - "$artifact_dir" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
metadata = [json.loads(path.read_text(encoding="utf-8")) for path in root.glob("*/metadata.json")]
classes = {item["classification"] for item in metadata}
if classes != {"PASS"}:
    raise SystemExit(f"unexpected classifications: {classes!r}")
if any(item["exit_code"] != 0 for item in metadata):
    raise SystemExit("expected all fast eval artifact exit codes to be 0")
for path in root.glob("*/output.txt"):
    if not path.read_text(encoding="utf-8").strip():
        raise SystemExit(f"empty output artifact: {path}")
PY

EVAL_ARTIFACT_DIR="$env_artifact_dir" scripts/agent-evals.sh --fast --artifact-dir "$cli_artifact_dir" >/tmp/agent-evals-artifacts-precedence.out

if find "$env_artifact_dir" -name metadata.json | grep -q .; then
  printf 'FAIL: EVAL_ARTIFACT_DIR received artifacts even though --artifact-dir was provided\n' >&2
  exit 1
fi
if ! find "$cli_artifact_dir" -name metadata.json | grep -q .; then
  printf 'FAIL: --artifact-dir did not receive artifacts\n' >&2
  exit 1
fi

printf 'PASS: agent-evals artifact output and CLI precedence verified (%s deterministic evals).\n' "$expected_count"
