# Bootstrap: gate candidate discovery into scripts/agent-eval.sh.

discover_gates_into_eval() {
  if [ "$discover_gates" != "1" ]; then
    return 0
  fi

  if [ "$dry_run" = "1" ]; then
    log "DRY-RUN python3 $TEMPLATE_ROOT/scripts/lib/insert_gate_candidates.py --target $TARGET_ROOT"
    return 0
  fi

  log ""
  log "Discovering candidate gate commands for $TARGET_ROOT ..."
  if ! python3 "$TEMPLATE_ROOT/scripts/lib/insert_gate_candidates.py" --target "$TARGET_ROOT"; then
    die "insert_gate_candidates.py failed; agent-eval.sh markers may be inconsistent"
  fi

  if agent_eval_has_candidate_stubs; then
    add_manifest_feature "gate-candidate-discovery"
  fi
}

agent_eval_has_candidate_stubs() {
  [ -f "$TARGET_ROOT/scripts/agent-eval.sh" ] || return 1
  grep -Eq '^[[:space:]]*#[[:space:]]{3}run[[:space:]]+\S' "$TARGET_ROOT/scripts/agent-eval.sh"
}

add_manifest_feature() {
  feature="$1"
  manifest_path="$TARGET_ROOT/.agent/manifest.json"
  [ -f "$manifest_path" ] || die "missing manifest for feature update: $manifest_path"
  FEATURE_NAME="$feature" MANIFEST_PATH="$manifest_path" python3 - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["MANIFEST_PATH"])
feature = os.environ["FEATURE_NAME"]
data = json.loads(path.read_text(encoding="utf-8"))
features = data.setdefault("features_enabled", [])
if feature not in features:
    features.append(feature)
path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PY
}
