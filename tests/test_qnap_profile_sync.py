from pathlib import PurePosixPath

import pytest

from tools.qnap_profile_sync import (
    QnapError,
    _raid_summary,
    qnap_connection_settings,
    smoke_root,
)


def test_raid_summary_reports_degraded_recovery():
    mdstat = """
md1 : active raid1 sda3[3] sdb3[2]
      3897064256 blocks super 1.0 [2/1] [U_]
      [====>................] recovery = 28.3% finish=407.9min

md256 : active raid1 sdb2[1] sda2[0]
      530112 blocks super 1.0 [2/2] [UU]
"""

    assert _raid_summary(mdstat) == {
        "array": "U_",
        "recovery_percent": 28.3,
    }


def test_smoke_root_is_confined_to_container_station_share():
    root = smoke_root(
        "/share/CACHEDEV3_DATA/.qpkg/container-station",
        "profile-sync-20260727",
    )

    assert root == PurePosixPath(
        "/share/CACHEDEV3_DATA/.mwodevelop-smoke/"
        "profile-sync-20260727"
    )


@pytest.mark.parametrize(
    "run_id",
    ("../escape", "/absolute", "two/slashes", "UPPERCASE", "x"),
)
def test_smoke_root_rejects_unsafe_run_id(run_id):
    with pytest.raises(QnapError, match="invalid smoke run id"):
        smoke_root(
            "/share/CACHEDEV3_DATA/.qpkg/container-station",
            run_id,
        )


def test_qnap_connection_requires_private_key_and_pinned_host(tmp_path):
    identity = tmp_path / "id_ed25519"
    identity.write_text("private", encoding="utf-8")
    identity.chmod(0o600)
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text("qnap ssh-ed25519 test\n", encoding="utf-8")
    known_hosts.chmod(0o600)

    settings = qnap_connection_settings(
        {
            "QNAP_HOST": "qnap",
            "QNAP_USER": "admin",
            "QNAP_SSH_KEY": str(identity),
            "QNAP_KNOWN_HOSTS": str(known_hosts),
            "QNAP_PASS": "must-not-be-used",
        }
    )

    assert settings["key_filename"] == str(identity)
    assert settings["known_hosts"] == str(known_hosts)
    assert "password" not in settings


def test_qnap_connection_rejects_broad_key_permissions(tmp_path):
    identity = tmp_path / "id_ed25519"
    identity.write_text("private", encoding="utf-8")
    identity.chmod(0o644)
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text("qnap ssh-ed25519 test\n", encoding="utf-8")
    known_hosts.chmod(0o600)

    with pytest.raises(QnapError, match="permissions are too broad"):
        qnap_connection_settings(
            {
                "QNAP_HOST": "qnap",
                "QNAP_USER": "admin",
                "QNAP_SSH_KEY": str(identity),
                "QNAP_KNOWN_HOSTS": str(known_hosts),
            }
        )
