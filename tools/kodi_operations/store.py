"""Private, symlink-safe and atomic run state persistence."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


RUN_ID = re.compile(r"^[0-9a-f]{32}$")


class StoreError(RuntimeError):
    pass


def _assert_not_symlink(path: Path) -> None:
    current = path
    while current != current.parent:
        if current.exists() and current.is_symlink():
            raise StoreError("private run path cannot contain a symlink")
        current = current.parent


def _atomic_json(path: Path, document: dict[str, Any]) -> None:
    _assert_not_symlink(path.parent)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".%s." % path.name,
        dir=str(path.parent),
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class RunStore:
    def __init__(self, repository: Path, run_id: str):
        if not RUN_ID.fullmatch(run_id):
            raise StoreError("invalid run ID")
        self.private_root = (
            Path(repository).resolve() / ".kodi-private" / "kodi-ops" / "runs"
        )
        _assert_not_symlink(self.private_root)
        self.root = self.private_root / run_id
        _assert_not_symlink(self.root)

    def create(self) -> None:
        self.root.mkdir(parents=True, exist_ok=False, mode=0o700)
        self.root.chmod(0o700)
        (self.root / "evidence").mkdir(mode=0o700)

    def write(self, name: str, document: dict[str, Any]) -> None:
        if name not in {"plan.json", "state.json", "report.json"}:
            raise StoreError("unsupported run document")
        _atomic_json(self.root / name, document)

    def read(self, name: str) -> dict[str, Any]:
        if name not in {"plan.json", "state.json", "report.json"}:
            raise StoreError("unsupported run document")
        path = self.root / name
        _assert_not_symlink(path)
        if not path.is_file():
            raise StoreError("run document is missing: %s" % name)
        return json.loads(path.read_text(encoding="utf-8"))

    def evidence_path(self, name: str) -> Path:
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,127}\.json", name):
            raise StoreError("invalid evidence name")
        return self.root / "evidence" / name

    def write_evidence(self, name: str, document: dict[str, Any]) -> None:
        _atomic_json(self.evidence_path(name), document)
