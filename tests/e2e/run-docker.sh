#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
docker build -f "$repo_root/tests/e2e/Dockerfile" -t mwo-kodi-e2e "$repo_root"
docker run --rm mwo-kodi-e2e
