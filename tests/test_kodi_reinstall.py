import hashlib
import sqlite3
import zipfile
from types import SimpleNamespace

import pytest

from tools.kodi_reinstall import (
    KODI_STORAGE_PATHS,
    RepositoryIndexNotReady,
    _start_kodi,
    apply_addon_origins,
    apk_abis,
    deploy_target,
    execute_kodi_builtin,
    file_digest,
    installed_addon_origins,
    installed_addon_origins_in_kodi,
    uninstall_and_clean,
)


def test_execute_kodi_builtin_prefers_jsonrpc(monkeypatch):
    calls = []

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def call(self, method, params):
            calls.append((method, params))

    monkeypatch.setattr(
        "tools.kodi_reinstall.AdbJsonRpcClient", lambda *_args: Client()
    )
    monkeypatch.setattr(
        "tools.kodi_reinstall.AdbEventClient",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("EventServer fallback was not expected")
        ),
    )

    assert (
        execute_kodi_builtin("adb", 5038, "serial", "UpdateAddonRepos")
        == "jsonrpc"
    )
    assert calls == [
        (
            "XBMC.ExecuteBuiltin",
            {"command": "UpdateAddonRepos", "wait": False},
        )
    ]


def test_execute_kodi_builtin_falls_back_to_eventserver(monkeypatch):
    calls = []

    class Client:
        def __enter__(self):
            raise RuntimeError("JSON-RPC unavailable")

        def __exit__(self, *_args):
            return None

    class Events:
        def execute_builtin(self, command):
            calls.append(command)

    monkeypatch.setattr(
        "tools.kodi_reinstall.AdbJsonRpcClient", lambda *_args: Client()
    )
    monkeypatch.setattr(
        "tools.kodi_reinstall.AdbEventClient", lambda *_args: Events()
    )

    assert (
        execute_kodi_builtin("adb", 5038, "serial", "UpdateAddonRepos")
        == "eventserver"
    )
    assert calls == ["UpdateAddonRepos"]


def test_start_kodi_enables_package_before_launcher(monkeypatch):
    commands = []
    options = []
    readiness = []

    monkeypatch.setattr(
        "tools.kodi_reinstall.adb_command",
        lambda *args, **kwargs: (
            commands.append(args[4]), options.append(kwargs)
        ),
    )
    monkeypatch.setattr(
        "tools.kodi_reinstall._wait_for_kodi_ready",
        lambda *args: readiness.append(args),
    )

    _start_kodi("adb", 5038, "serial")

    assert commands == [
        "cmd package unsuspend org.xbmc.kodi",
        "input keyevent KEYCODE_WAKEUP",
        "pm enable org.xbmc.kodi",
        "monkey -p org.xbmc.kodi "
        "-c android.intent.category.LAUNCHER 1 >/dev/null",
    ]
    assert options[0] == {"check": False}
    assert options[1] == {"check": False}
    assert readiness == [("adb", 5038, "serial")]


def test_apk_inventory_and_digest(tmp_path):
    apk = tmp_path / "kodi.apk"
    with zipfile.ZipFile(apk, "w") as archive:
        archive.writestr("lib/armeabi-v7a/libkodi.so", b"arm")
        archive.writestr("lib/x86/libkodi.so", b"x86")
        archive.writestr("assets/addons.xml", b"<addons/>")

    assert apk_abis(apk) == ["armeabi-v7a", "x86"]
    assert file_digest(apk) == hashlib.sha256(apk.read_bytes()).hexdigest()


def test_uninstall_cleans_only_explicit_kodi_paths(monkeypatch):
    calls = []

    def command(*args, **kwargs):
        calls.append((args, kwargs))
        command_text = args[4] if len(args) > 4 else ""
        if command_text.startswith("pm path"):
            return SimpleNamespace(stdout="package:/data/app/base.apk\n")
        if args[3] == "uninstall":
            return SimpleNamespace(stdout="Success\n")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr("tools.kodi_reinstall.adb_command", command)
    monkeypatch.setattr(
        "tools.kodi_reinstall.adb_output",
        lambda *_args, **_kwargs: "",
    )

    uninstall_and_clean("adb", 5038, "serial")

    cleanup = next(
        args[4]
        for args, _kwargs in calls
        if len(args) > 4 and args[4].startswith("rm -rf")
    )
    assert all("'%s'" % path in cleanup for path in KODI_STORAGE_PATHS)
    assert "/sdcard/Android/data/org.xbmc.kodi" in cleanup


def test_uninstall_fails_if_kodi_storage_remains(monkeypatch):
    monkeypatch.setattr(
        "tools.kodi_reinstall.adb_command",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=""),
    )
    monkeypatch.setattr(
        "tools.kodi_reinstall.adb_output",
        lambda *_args, **_kwargs: KODI_STORAGE_PATHS[0],
    )

    with pytest.raises(RuntimeError, match="left data behind"):
        uninstall_and_clean("adb", 5038, "serial")


def test_origin_read_falls_back_to_in_kodi_for_scoped_storage(monkeypatch):
    monkeypatch.setattr(
        "tools.kodi_reinstall.addon_database_path",
        lambda *_args: (_ for _ in ()).throw(
            RuntimeError("Kodi add-on database was not found")
        ),
    )
    monkeypatch.setattr(
        "tools.kodi_reinstall.installed_addon_origins_in_kodi",
        lambda *_args, **_kwargs: {
            "plugin.video.umbrella": "repository.mwodevelop"
        },
    )

    assert installed_addon_origins(
        "adb",
        5037,
        "serial",
        ["plugin.video.umbrella"],
        origin_script="origin-script",
    ) == {"plugin.video.umbrella": "repository.mwodevelop"}


def test_in_kodi_origin_read_retries_dropped_builtin_command(monkeypatch):
    clock = [0]
    executions = []

    def execute(_adb, _port, _serial, command):
        executions.append(command)
        return "jsonrpc"

    def command(*args, **_kwargs):
        remote = args[4] if len(args) > 4 else ""
        if remote.startswith("cat ") and len(executions) >= 2:
            return SimpleNamespace(
                returncode=0,
                stdout=(
                    '{"ok":true,"origins":'
                    '{"plugin.video.umbrella":"repository.mwodevelop"}}'
                ),
            )
        return SimpleNamespace(returncode=1, stdout="")

    monkeypatch.setattr("tools.kodi_reinstall.adb_command", command)
    monkeypatch.setattr("tools.kodi_reinstall.execute_kodi_builtin", execute)
    monkeypatch.setattr(
        "tools.kodi_reinstall.time.monotonic",
        lambda: clock[0],
    )
    monkeypatch.setattr(
        "tools.kodi_reinstall.time.sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )

    origins = installed_addon_origins_in_kodi(
        "adb",
        5038,
        "serial",
        ["plugin.video.umbrella"],
        "origin-script",
        timeout=30,
    )

    assert origins == {
        "plugin.video.umbrella": "repository.mwodevelop"
    }
    assert len(executions) == 2


def test_deploy_uses_direct_adb_restore_mode(monkeypatch):
    calls = []
    target = {
        "serial": "serial",
        "apk": "kodi.apk",
        "expected_version": "21.3",
        "restore_mode": "adb-push",
        "addon_origins": {},
    }
    monkeypatch.setattr(
        "tools.kodi_reinstall.uninstall_and_clean",
        lambda *_args: calls.append("clean"),
    )
    monkeypatch.setattr(
        "tools.kodi_reinstall.install_apk",
        lambda *_args: calls.append("install"),
    )
    monkeypatch.setattr(
        "tools.kodi_reinstall.restore_snapshot_via_adb",
        lambda *_args: calls.append("restore") or {"snapshot_id": "id"},
    )
    monkeypatch.setattr(
        "tools.kodi_reinstall.validate_restored_target",
        lambda *_args: calls.append("validate") or {"result": "pass"},
    )
    monkeypatch.setattr(
        "tools.kodi_reinstall.reconcile_default_addons",
        lambda *_args: calls.append("defaults"),
    )
    monkeypatch.setattr(
        "tools.kodi_reinstall.reconcile_private_addons",
        lambda *_args: calls.append("private") or [],
    )

    assert deploy_target(
        "adb",
        5038,
        target,
        "device-script",
        "origin-script",
    ) == {
        "result": "pass"
    }
    assert calls == [
        "clean",
        "install",
        "restore",
        "defaults",
        "private",
        "validate",
    ]


def create_addons_database(path, installed_origin=""):
    connection = sqlite3.connect(path)
    with connection:
        connection.executescript(
            """
            CREATE TABLE installed (addonID TEXT, origin TEXT);
            CREATE TABLE repo (
                id INTEGER PRIMARY KEY,
                addonID TEXT,
                checksum TEXT
            );
            CREATE TABLE addons (
                id INTEGER PRIMARY KEY,
                addonID TEXT,
                version TEXT
            );
            CREATE TABLE addonlinkrepo (idRepo INTEGER, idAddon INTEGER);
            INSERT INTO installed VALUES ('plugin.video.umbrella', '');
            INSERT INTO repo VALUES (
                1, 'repository.mwodevelop', 'checksum'
            );
            INSERT INTO addons VALUES (
                1, 'plugin.video.umbrella', '6.7.81.16'
            );
            INSERT INTO addonlinkrepo VALUES (1, 1);
            """
        )
        connection.execute(
            "UPDATE installed SET origin=?",
            (installed_origin,),
        )
    connection.close()


def test_origin_is_assigned_only_from_an_indexed_repository(tmp_path):
    database = tmp_path / "Addons33.db"
    create_addons_database(database)

    apply_addon_origins(
        database,
        {"plugin.video.umbrella": "repository.mwodevelop"},
    )

    connection = sqlite3.connect(database)
    origin = connection.execute(
        "SELECT origin FROM installed WHERE addonID='plugin.video.umbrella'"
    ).fetchone()[0]
    connection.close()
    assert origin == "repository.mwodevelop"


def test_origin_assignment_rejects_another_origin(tmp_path):
    database = tmp_path / "Addons33.db"
    create_addons_database(database, "repository.someone-else")

    with pytest.raises(RuntimeError, match="different origin"):
        apply_addon_origins(
            database,
            {"plugin.video.umbrella": "repository.mwodevelop"},
        )


def test_origin_assignment_waits_for_repository_index(tmp_path):
    database = tmp_path / "Addons33.db"
    create_addons_database(database)
    connection = sqlite3.connect(database)
    with connection:
        connection.execute("UPDATE repo SET checksum=''")
    connection.close()

    with pytest.raises(RepositoryIndexNotReady):
        apply_addon_origins(
            database,
            {"plugin.video.umbrella": "repository.mwodevelop"},
        )


def test_origin_migration_requires_matching_indexed_versions(tmp_path):
    database = tmp_path / "Addons33.db"
    create_addons_database(database, "repository.mwodevelop.testing")
    connection = sqlite3.connect(database)
    with connection:
        connection.execute(
            "INSERT INTO repo VALUES (?, ?, ?)",
            (2, "repository.mwodevelop.testing", "b" * 64),
        )
        connection.execute(
            "INSERT INTO addons VALUES (?, ?, ?)",
            (2, "plugin.video.umbrella", "6.7.81.16"),
        )
        connection.execute("INSERT INTO addonlinkrepo VALUES (2, 2)")
        connection.execute(
            "UPDATE repo SET checksum=? WHERE id=1",
            ("a" * 64,),
        )
    connection.close()

    apply_addon_origins(
        database,
        {"plugin.video.umbrella": "repository.mwodevelop"},
        {
            "plugin.video.umbrella": "repository.mwodevelop.testing"
        },
        {
            "repository.mwodevelop": "a" * 64,
            "repository.mwodevelop.testing": "b" * 64,
        },
    )

    connection = sqlite3.connect(database)
    origin = connection.execute(
        "SELECT origin FROM installed WHERE addonID='plugin.video.umbrella'"
    ).fetchone()[0]
    connection.close()
    assert origin == "repository.mwodevelop"


def test_origin_migration_retries_a_stale_candidate_version(tmp_path):
    database = tmp_path / "Addons33.db"
    create_addons_database(database, "repository.mwodevelop.testing")
    connection = sqlite3.connect(database)
    with connection:
        connection.execute(
            "INSERT INTO repo VALUES (?, ?, ?)",
            (2, "repository.mwodevelop.testing", "b" * 64),
        )
        connection.execute(
            "INSERT INTO addons VALUES (?, ?, ?)",
            (2, "plugin.video.umbrella", "6.7.81.15"),
        )
        connection.execute("INSERT INTO addonlinkrepo VALUES (2, 2)")
    connection.close()

    with pytest.raises(RepositoryIndexNotReady, match="candidates differ"):
        apply_addon_origins(
            database,
            {"plugin.video.umbrella": "repository.mwodevelop"},
            {
                "plugin.video.umbrella": "repository.mwodevelop.testing"
            },
        )


def test_origin_migration_allows_exact_explicit_canary_transition(tmp_path):
    database = tmp_path / "Addons33.db"
    create_addons_database(database, "repository.mwodevelop")
    connection = sqlite3.connect(database)
    with connection:
        connection.execute(
            "INSERT INTO repo VALUES (2, ?, ?)",
            ("repository.mwodevelop.testing", "b" * 64),
        )
        connection.execute(
            "INSERT INTO addons VALUES (2, ?, ?)",
            ("plugin.video.umbrella", "6.7.81.17"),
        )
        connection.execute("INSERT INTO addonlinkrepo VALUES (2, 2)")
        connection.execute(
            "UPDATE repo SET checksum=? WHERE id=1",
            ("a" * 64,),
        )
    connection.close()

    apply_addon_origins(
        database,
        {"plugin.video.umbrella": "repository.mwodevelop.testing"},
        {"plugin.video.umbrella": "repository.mwodevelop"},
        {
            "repository.mwodevelop": "a" * 64,
            "repository.mwodevelop.testing": "b" * 64,
        },
        {
            "plugin.video.umbrella": {
                "from": "6.7.81.16",
                "to": "6.7.81.17",
            }
        },
    )

    connection = sqlite3.connect(database)
    origin = connection.execute(
        "SELECT origin FROM installed WHERE addonID='plugin.video.umbrella'"
    ).fetchone()[0]
    connection.close()
    assert origin == "repository.mwodevelop.testing"


def test_origin_migration_rejects_unexpected_repository_checksum(tmp_path):
    database = tmp_path / "Addons33.db"
    create_addons_database(database)

    with pytest.raises(RepositoryIndexNotReady, match="checksum differs"):
        apply_addon_origins(
            database,
            {"plugin.video.umbrella": "repository.mwodevelop"},
            repository_checksums={
                "repository.mwodevelop": "a" * 64,
            },
        )
