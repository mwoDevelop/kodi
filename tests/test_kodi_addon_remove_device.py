import importlib.util
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_remove_runner_has_standalone_cli():
    result = subprocess.run(
        [
            sys.executable,
            str(
                Path(__file__).parents[1]
                / "tools/kodi_addon_remove.py"
            ),
            "--help",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--addon-id" in result.stdout


def load_remove(monkeypatch, tmp_path):
    home = tmp_path / "home"
    database = tmp_path / "database"

    def translate(path):
        if path == "special://home/addons":
            return str(home / "addons")
        if path == "special://database":
            return str(database)
        if path.startswith("special://profile/addon_data/"):
            addon_id = path.rsplit("/", 1)[-1]
            return str(home / "userdata/addon_data" / addon_id)
        raise AssertionError("unexpected Kodi path")

    monkeypatch.setitem(
        sys.modules,
        "xbmcvfs",
        SimpleNamespace(translatePath=translate),
    )
    path = Path(__file__).parents[1] / "tools/kodi_addon_remove_device.py"
    spec = importlib.util.spec_from_file_location(
        "kodi_addon_remove_device_test",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, home, database


def create_database(path, repository, dependent=None):
    path.parent.mkdir(parents=True)
    connection = sqlite3.connect(path)
    with connection:
        connection.executescript(
            """
            CREATE TABLE addonlinkrepo (idRepo integer, idAddon integer);
            CREATE TABLE installed (
                id INTEGER PRIMARY KEY,
                addonID TEXT UNIQUE,
                enabled BOOLEAN,
                origin TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE package (
                id integer primary key,
                addonID text,
                filename text,
                hash text
            );
            CREATE TABLE repo (
                id integer primary key,
                addonID text,
                checksum text
            );
            CREATE TABLE update_rules (
                id integer primary key,
                addonID TEXT,
                updateRule INTEGER
            );
            """
        )
        connection.execute(
            "INSERT INTO installed(addonID,enabled,origin) VALUES(?,?,?)",
            (repository, 0, ""),
        )
        connection.execute(
            "INSERT INTO repo(id,addonID,checksum) VALUES(1,?,?)",
            (repository, "a" * 64),
        )
        connection.execute("INSERT INTO addonlinkrepo VALUES(1,7)")
        connection.execute(
            "INSERT INTO package(addonID,filename,hash) VALUES(?,?,?)",
            (repository, repository + "-1.0.0.zip", "b" * 64),
        )
        connection.execute(
            "INSERT INTO update_rules(addonID,updateRule) VALUES(?,?)",
            (repository, 1),
        )
        if dependent:
            connection.execute(
                "INSERT INTO installed(addonID,enabled,origin) VALUES(?,?,?)",
                (dependent, 1, repository),
            )
    connection.close()


def test_remove_addon_cleans_directory_database_and_package(
    monkeypatch, tmp_path
):
    module, home, database = load_remove(monkeypatch, tmp_path)
    addon = "repository.mwodevelop.testing"
    target = home / "addons" / addon
    target.mkdir(parents=True)
    (target / "addon.xml").write_text("<addon/>", encoding="utf-8")
    addon_data = home / "userdata/addon_data" / addon
    addon_data.mkdir(parents=True)
    (addon_data / "settings.xml").write_text("<settings/>", encoding="utf-8")
    packages = home / "addons" / "packages"
    packages.mkdir()
    (packages / (addon + "-1.0.0.zip")).write_bytes(b"zip")
    db = database / "Addons33.db"
    create_database(db, addon)

    result = module._remove(addon)

    assert result == {
        "addon_data_removed": True,
        "directory_removed": True,
        "packages_removed": 1,
        "repository_rows": 1,
    }
    assert not target.exists()
    assert not addon_data.exists()
    assert not (packages / (addon + "-1.0.0.zip")).exists()
    connection = sqlite3.connect(db)
    assert connection.execute("SELECT * FROM installed").fetchall() == []
    assert connection.execute("SELECT * FROM repo").fetchall() == []
    assert connection.execute("SELECT * FROM addonlinkrepo").fetchall() == []
    assert connection.execute("SELECT * FROM package").fetchall() == []
    assert connection.execute("SELECT * FROM update_rules").fetchall() == []
    connection.close()


def test_remove_repository_refuses_owned_addons_and_restores_directory(
    monkeypatch, tmp_path
):
    module, home, database = load_remove(monkeypatch, tmp_path)
    addon = "repository.mwodevelop.testing"
    target = home / "addons" / addon
    target.mkdir(parents=True)
    (target / "addon.xml").write_text("<addon/>", encoding="utf-8")
    create_database(
        database / "Addons33.db",
        addon,
        dependent="script.module.mwoscrapers",
    )

    with pytest.raises(RuntimeError, match="still owns"):
        module._remove(addon)

    assert target.is_dir()
    assert (target / "addon.xml").is_file()
    assert not Path(str(target) + ".mwo-remove").exists()
