#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
e2e_root="$repo_root/.e2e"
first="$e2e_root/first"
second="$e2e_root/second"
python_bin="${PYTHON:-python3}"

if [[ -x "$repo_root/.venv/bin/python" && -z "${PYTHON:-}" ]]; then
  python_bin="$repo_root/.venv/bin/python"
fi

rm -rf "$e2e_root"
mkdir -p "$e2e_root"
"$python_bin" "$repo_root/tools/build_repo.py" --output "$first"
"$python_bin" "$repo_root/tools/build_repo.py" --output "$second"
diff -r "$first" "$second"
"$python_bin" -m pytest -q "$repo_root/tests"
