import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest


def load_apply(monkeypatch, tmp_path):
    home = tmp_path / "home"
    temp = tmp_path / "temp"

    def translate(path):
        if path == "special://home/addons":
            return str(home / "addons")
        if path == "special://temp/mwodevelop-candidate":
            return str(temp / "mwodevelop-candidate")
        raise AssertionError("unexpected Kodi path")

    monkeypatch.setitem(
        sys.modules,
        "xbmcvfs",
        SimpleNamespace(translatePath=translate),
    )
    path = Path(__file__).parent / "e2e/kodi_addon_candidate_apply.py"
    spec = importlib.util.spec_from_file_location(
        "kodi_addon_candidate_apply_test",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, home, temp


def test_candidate_apply_replaces_exact_addon_atomically(
    monkeypatch, tmp_path
):
    module, home, temp = load_apply(monkeypatch, tmp_path)
    addon_id = "script.module.mwoscrapers"
    target = home / "addons" / addon_id
    target.mkdir(parents=True)
    (target / "addon.xml").write_text(
        f'<addon id="{addon_id}" version="0.1.6"/>',
        encoding="utf-8",
    )
    (target / "old.py").write_text("old\n", encoding="utf-8")
    candidate = tmp_path / "candidate.zip"
    with ZipFile(candidate, "w") as archive:
        archive.writestr(
            f"{addon_id}/addon.xml",
            f'<addon id="{addon_id}" version="0.1.7"/>',
        )
        archive.writestr(f"{addon_id}/lib/new.py", "new\n")

    result = module._apply(candidate, addon_id, "0.1.7")

    assert result == {
        "files": 2,
        "version": "0.1.7",
        "repaired_orphan": False,
    }
    assert module._identity(target / "addon.xml") == (addon_id, "0.1.7")
    assert (target / "lib/new.py").read_text(encoding="utf-8") == "new\n"
    assert not (target / "old.py").exists()
    assert not list(
        (temp / "mwodevelop-candidate").glob("backup-%s-*" % addon_id)
    )


def test_candidate_apply_ignores_stale_work_directories(monkeypatch, tmp_path):
    module, home, temp = load_apply(monkeypatch, tmp_path)
    addon_id = "repository.rapideo_pl"
    target = home / "addons" / addon_id
    target.mkdir(parents=True)
    (target / "addon.xml").write_text(
        f'<addon id="{addon_id}" version="1.0.3"/>',
        encoding="utf-8",
    )
    work = temp / "mwodevelop-candidate"
    stale = work / ("backup-" + addon_id)
    stale.mkdir(parents=True)
    (stale / "leftover").write_text("old", encoding="utf-8")
    candidate = tmp_path / "candidate.zip"
    with ZipFile(candidate, "w") as archive:
        archive.writestr(
            f"{addon_id}/addon.xml",
            f'<addon id="{addon_id}" version="1.0.4"/>',
        )

    result = module._apply(candidate, addon_id, "1.0.4")

    assert result == {
        "files": 1,
        "version": "1.0.4",
        "repaired_orphan": False,
    }
    assert module._identity(target / "addon.xml") == (addon_id, "1.0.4")
    assert (stale / "leftover").read_text(encoding="utf-8") == "old"


def test_candidate_apply_rejects_archive_escape(monkeypatch, tmp_path):
    module, _home, _temp = load_apply(monkeypatch, tmp_path)
    candidate = tmp_path / "unsafe.zip"
    with ZipFile(candidate, "w") as archive:
        archive.writestr("../outside", "unsafe")

    with pytest.raises(ValueError, match="unsafe candidate archive path"):
        module._apply(
            candidate,
            "script.module.mwoscrapers",
            "0.1.7",
        )


def test_candidate_apply_repairs_identity_verified_orphan(
    monkeypatch, tmp_path
):
    module, home, _temp = load_apply(monkeypatch, tmp_path)
    addon_id = "repository.rapideo_pl"
    target = home / "addons" / addon_id
    target.mkdir(parents=True)
    (target / "addon.xml").write_text(
        f'<addon id="{addon_id}" version="1.0.3"/>', encoding="utf-8"
    )
    candidate = tmp_path / "candidate.zip"
    with ZipFile(candidate, "w") as archive:
        archive.writestr(
            f"{addon_id}/addon.xml",
            f'<addon id="{addon_id}" version="1.0.4"/>',
        )
    original_replace = module.os.replace

    def replace(source, destination):
        if Path(source) == target:
            raise PermissionError("simulated scoped-storage orphan")
        return original_replace(source, destination)

    monkeypatch.setattr(module.os, "replace", replace)

    result = module._apply(
        candidate, addon_id, "1.0.4", repair_orphan=True
    )

    assert result["repaired_orphan"] is True
    assert module._identity(target / "addon.xml") == (addon_id, "1.0.4")
