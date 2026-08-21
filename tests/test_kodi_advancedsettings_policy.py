from pathlib import Path
from types import SimpleNamespace

from tools.kodi_advancedsettings_policy import (
    REMOTE_ADVANCEDSETTINGS,
    REMOTE_STAGING,
    reconcile_android_advancedsettings,
    sanitize_advancedsettings,
)


def test_sanitizer_removes_only_remote_library_databases():
    payload = b"""<advancedsettings>
  <cache><memorysize>1</memorysize></cache>
  <videodatabase><host>nas</host><pass>secret</pass></videodatabase>
  <musicdatabase><host>nas</host><pass>secret</pass></musicdatabase>
  <videolibrary><importwatchedstate>true</importwatchedstate></videolibrary>
</advancedsettings>"""

    output, removed = sanitize_advancedsettings(payload)

    assert removed == ("musicdatabase", "videodatabase")
    assert b"database" not in output
    assert b"<cache>" in output
    assert b"<videolibrary>" in output
    assert b"secret" not in output


def test_sanitizer_is_an_exact_no_op_without_remote_databases():
    payload = b"<advancedsettings><cache /></advancedsettings>\n"
    assert sanitize_advancedsettings(payload) == (payload, ())


def test_android_reconcile_updates_and_verifies_atomically(monkeypatch, tmp_path):
    remote = b"<advancedsettings><cache /><videodatabase /></advancedsettings>"
    written = []

    def adb_command(_adb, _port, _serial, *args, **_kwargs):
        if args == ("shell", "test -f '%s'" % REMOTE_ADVANCEDSETTINGS):
            return SimpleNamespace(returncode=0)
        if args[0] == "pull":
            destination = Path(args[2])
            destination.write_bytes(written[-1] if written else remote)
            return SimpleNamespace(returncode=0)
        if args[0] == "push":
            written.append(Path(args[1]).read_bytes())
            return SimpleNamespace(returncode=0)
        if args == (
            "shell",
            "mv -f '%s' '%s'" % (REMOTE_STAGING, REMOTE_ADVANCEDSETTINGS),
        ):
            return SimpleNamespace(returncode=0)
        if args == ("shell", "rm -f '%s'" % REMOTE_STAGING):
            return SimpleNamespace(returncode=0)
        raise AssertionError(args)

    monkeypatch.setattr(
        "tools.kodi_advancedsettings_policy.adb_command", adb_command
    )

    result = reconcile_android_advancedsettings("adb", 5038, "device")

    assert result["status"] == "UPDATED"
    assert result["removed"] == ["videodatabase"]
    assert b"videodatabase" not in written[-1]
