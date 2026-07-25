#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
result_root="$repo_root/.e2e/upstream-sync"
python_bin="${PYTHON:-python3}"

if [[ -x "$repo_root/.venv/bin/python" && -z "${PYTHON:-}" ]]; then
  python_bin="$repo_root/.venv/bin/python"
fi

mkdir -p "$result_root"

"$python_bin" -m tools.upstream_sync.cli validate-config
"$python_bin" -m tools.upstream_sync.cli discover \
  --output "$result_root/discovery-first.json" \
  --markdown "$result_root/discovery.md"
"$python_bin" -m tools.upstream_sync.cli discover \
  --output "$result_root/discovery-second.json"
cmp "$result_root/discovery-first.json" "$result_root/discovery-second.json"

"$python_bin" - "$result_root/discovery-first.json" <<'PY'
import json
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
unexpected = [
    (source["component"], source["action"])
    for source in report["sources"]
    if source["action"] != "noop"
]
if unexpected:
    raise SystemExit("upstream baseline is not a no-op: %r" % unexpected)
PY

(
  cd "$repo_root/umbrella"
  .venv-downstream/bin/python tools/rebuild_downstream.py --check
  .venv-downstream/bin/python -m pytest -q
)
(
  cd "$repo_root/watchnixtoons2"
  python3 tools/import_mwodevelop_watchnixtoons2.py --check >/dev/null
  python3 -m unittest discover -s mwodevelop/tests -q
)
(
  cd "$repo_root/mwoscrapers"
  .venv/bin/python tools/discover_upstreams.py \
    --output "$result_root/provider-discovery.json"
  .venv/bin/python tools/check_upstreams.py \
    --output "$result_root/provider-audit" \
    --markdown "$result_root/provider-audit.md"
  .venv/bin/python -m pytest -q
)

"$repo_root/tests/e2e/run.sh"

git -C "$repo_root" diff --exit-code -- manifests/locks/stable.json
echo "Upstream synchronization E2E passed; stable lock was not modified."
