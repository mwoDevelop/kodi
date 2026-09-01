import base64
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest


def context(enabled=True, origin="repository.mwodevelop"):
    payload = json.dumps(
        {"enabled": enabled, "origin": origin},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def load_apply(monkeypatch, tmp_path):
    home = tmp_path / "home"

    def translate(path):
        if path == "special://home/addons":
            return str(home / "addons")
        if path == "special://home/.mwodevelop-transactions":
            return str(home / ".mwodevelop-transactions")
        raise AssertionError("unexpected Kodi path")

    monkeypatch.setitem(
        sys.modules,
        "xbmcvfs",
        SimpleNamespace(translatePath=translate),
    )
    path = (
        Path(__file__).parents[1]
        / "tools/device/kodi_addon_transaction.py"
    )
    spec = importlib.util.spec_from_file_location(
        "kodi_addon_transaction_test", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, home


def candidate_zip(path, addon_id, version):
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "%s/addon.xml" % addon_id,
            '<addon id="%s" version="%s"/>' % (addon_id, version),
        )
        archive.writestr("%s/lib/new.py" % addon_id, "new\n")
    return path


def installed_addon(home, addon_id, version):
    target = home / "addons" / addon_id
    target.mkdir(parents=True)
    (target / "addon.xml").write_text(
        '<addon id="%s" version="%s"/>' % (addon_id, version),
        encoding="utf-8",
    )
    (target / "old.py").write_text("old\n", encoding="utf-8")
    return target


def test_transaction_requires_verify_before_commit_and_commits_exact_addon(
    monkeypatch, tmp_path
):
    module, home = load_apply(monkeypatch, tmp_path)
    addon_id = "script.module.mwoscrapers"
    target = installed_addon(home, addon_id, "0.1.6")
    candidate = candidate_zip(tmp_path / "candidate.zip", addon_id, "0.1.7")

    prepared = module._prepare(
        candidate, addon_id, "0.1.7", context(), repair_orphan=False
    )

    assert prepared["status"] == "ACTIVATED"
    assert module._identity(target / "addon.xml") == (addon_id, "0.1.7")
    status = module._status(addon_id)
    assert status["status"] == "ACTIVATED"
    assert status["previous"] == {
        "exists": True,
        "enabled": True,
        "origin": "repository.mwodevelop",
        "version": "0.1.6",
    }
    with pytest.raises(RuntimeError, match="not verified"):
        module._commit(addon_id)
    verified = module._verify(addon_id, "0.1.7", context())
    assert verified["status"] == "VERIFIED"
    committed = module._commit(addon_id)
    assert committed["status"] == "COMMITTED"
    assert module._status(addon_id)["status"] == "NO_CHANGE"
    assert not (target / "old.py").exists()


def test_interrupted_transaction_is_discoverable_and_rollback_restores_previous(
    monkeypatch, tmp_path
):
    module, home = load_apply(monkeypatch, tmp_path)
    addon_id = "repository.rapideo_pl"
    target = installed_addon(home, addon_id, "1.0.3")
    candidate = candidate_zip(tmp_path / "candidate.zip", addon_id, "1.0.4")
    module._prepare(candidate, addon_id, "1.0.4", context(False, None))

    with pytest.raises(RuntimeError, match="RECOVERY_REQUIRED"):
        module._prepare(candidate, addon_id, "1.0.4", context(False, None))
    rolled_back = module._rollback(addon_id)

    assert rolled_back["status"] == "ROLLED_BACK"
    assert module._identity(target / "addon.xml") == (addon_id, "1.0.3")
    assert (target / "old.py").read_text(encoding="utf-8") == "old\n"
    assert module._status(addon_id)["status"] == "NO_CHANGE"


def test_transaction_rolls_back_a_new_addon_to_absence(monkeypatch, tmp_path):
    module, home = load_apply(monkeypatch, tmp_path)
    addon_id = "plugin.video.new"
    candidate = candidate_zip(tmp_path / "candidate.zip", addon_id, "1.0.0")
    module._prepare(candidate, addon_id, "1.0.0", context(None, None))

    module._rollback(addon_id)

    assert not (home / "addons" / addon_id).exists()


def test_transaction_rejects_archive_escape(monkeypatch, tmp_path):
    module, _home = load_apply(monkeypatch, tmp_path)
    candidate = tmp_path / "unsafe.zip"
    with ZipFile(candidate, "w") as archive:
        archive.writestr("../outside", "unsafe")

    with pytest.raises(ValueError, match="unsafe candidate archive path"):
        module._prepare(
            candidate,
            "script.module.mwoscrapers",
            "0.1.7",
            context(),
        )


def test_transaction_repairs_identity_verified_orphan(monkeypatch, tmp_path):
    module, home = load_apply(monkeypatch, tmp_path)
    addon_id = "repository.rapideo_pl"
    target = installed_addon(home, addon_id, "1.0.3")
    candidate = candidate_zip(tmp_path / "candidate.zip", addon_id, "1.0.4")
    original_replace = module.os.replace

    def replace(source, destination):
        if Path(source) == target:
            raise PermissionError("simulated scoped-storage orphan")
        return original_replace(source, destination)

    monkeypatch.setattr(module.os, "replace", replace)
    result = module._prepare(
        candidate,
        addon_id,
        "1.0.4",
        context(),
        repair_orphan=True,
    )

    assert result["repaired_orphan"] is True
    assert module._identity(target / "addon.xml") == (addon_id, "1.0.4")
    module._verify(addon_id, "1.0.4", context())
    module._commit(addon_id)


def test_rollback_preserves_previous_tree_when_crash_precedes_backup(
    monkeypatch, tmp_path
):
    module, home = load_apply(monkeypatch, tmp_path)
    addon_id = "plugin.video.previous"
    target = installed_addon(home, addon_id, "1.0.0")
    candidate = candidate_zip(tmp_path / "candidate.zip", addon_id, "2.0.0")
    original_replace = module.os.replace

    def replace(source, destination):
        if Path(source) == target:
            raise OSError("simulated crash before backup")
        return original_replace(source, destination)

    monkeypatch.setattr(module.os, "replace", replace)
    with pytest.raises(OSError, match="simulated crash"):
        module._prepare(candidate, addon_id, "2.0.0", context())

    result = module._rollback(addon_id)
    assert result["status"] == "ROLLED_BACK"
    assert module._identity(target / "addon.xml") == (addon_id, "1.0.0")


def test_orphan_stage_without_journal_is_recoverable(monkeypatch, tmp_path):
    module, home = load_apply(monkeypatch, tmp_path)
    addon_id = "plugin.video.staged"
    transaction = home / ".mwodevelop-transactions" / addon_id
    transaction.mkdir(parents=True)
    (transaction / "staging").mkdir()

    assert module._status(addon_id)["status"] == "RECOVERY_REQUIRED"
    assert module._rollback(addon_id)["status"] == "ROLLED_BACK"
    assert module._status(addon_id)["status"] == "NO_CHANGE"
