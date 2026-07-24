#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
e2e_root="$repo_root/.e2e"
first="$e2e_root/first"
second="$e2e_root/second"

rm -rf "$e2e_root"
mkdir -p "$e2e_root"
python3 "$repo_root/tools/build_repo.py" --output "$first"
python3 "$repo_root/tools/build_repo.py" --output "$second"
diff -r "$first" "$second"
python3 -m pytest -q "$repo_root/tests"
