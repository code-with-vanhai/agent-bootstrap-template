#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

artifact_dir="$(mktemp -d /tmp/agent-evals-artifacts.XXXXXX)"
cleanup() {
  rm -rf "$artifact_dir"
}
trap cleanup EXIT

scripts/agent-evals.sh --fast --artifact-dir "$artifact_dir" >/tmp/agent-evals-artifacts.out

metadata_count="$(find "$artifact_dir" -name metadata.json | wc -l | tr -d '[:space:]')"
if [ "$metadata_count" -ne 4 ]; then
  printf 'FAIL: expected 4 metadata files, got %s\n' "$metadata_count" >&2
  find "$artifact_dir" -maxdepth 3 -type f | sort >&2
  exit 1
fi

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

env_artifact_dir="$(mktemp -d /tmp/agent-evals-env-artifacts.XXXXXX)"
cli_artifact_dir="$(mktemp -d /tmp/agent-evals-cli-artifacts.XXXXXX)"
trap 'rm -rf "$artifact_dir" "$env_artifact_dir" "$cli_artifact_dir"' EXIT

EVAL_ARTIFACT_DIR="$env_artifact_dir" scripts/agent-evals.sh --fast --artifact-dir "$cli_artifact_dir" >/tmp/agent-evals-artifacts-precedence.out

if find "$env_artifact_dir" -name metadata.json | grep -q .; then
  printf 'FAIL: EVAL_ARTIFACT_DIR received artifacts even though --artifact-dir was provided\n' >&2
  exit 1
fi
if ! find "$cli_artifact_dir" -name metadata.json | grep -q .; then
  printf 'FAIL: --artifact-dir did not receive artifacts\n' >&2
  exit 1
fi

printf 'PASS: agent-evals artifact output and CLI precedence verified.\n'
