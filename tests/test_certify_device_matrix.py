import subprocess

import pytest

from tools.certify_device_matrix import (
    TESTING_ORIGIN,
    _addon_state,
    _allowed_origins,
    _forwarded_port,
    _recover_kodi,
    _redacted_diagnostic,
    _run_functional_check,
)


def test_changed_bytes_require_testing_but_identical_bytes_accept_stable():
    testing = {
        "changed": {"zip_sha256": "a" * 64},
        "unchanged": {"zip_sha256": "b" * 64},
    }
    stable = {
        "changed": {"zip_sha256": "c" * 64},
        "unchanged": {"zip_sha256": "b" * 64},
    }

    allowed = _allowed_origins(testing, stable)

    assert allowed["changed"] == {TESTING_ORIGIN}
    assert allowed["unchanged"] == {
        TESTING_ORIGIN,
        "repository.mwodevelop",
    }


def test_dynamic_forward_port_is_validated():
    assert _forwarded_port("46454\n") == 46454

    for invalid in ("", "tcp:46454", "0", "65536", "-1"):
        with pytest.raises(RuntimeError, match="dynamic forward port"):
            _forwarded_port(invalid)


def test_addon_state_uses_kodi_for_scoped_profile(monkeypatch):
    expected = {
        "changed": {"version": "2.0", "zip_sha256": "a" * 64},
        "unchanged": {"version": "1.0", "zip_sha256": "b" * 64},
    }
    stable = {
        "changed": {"version": "1.0", "zip_sha256": "c" * 64},
        "unchanged": {"version": "1.0", "zip_sha256": "b" * 64},
    }
    versions = {"changed": "2.0", "unchanged": "1.0"}
    calls = []

    class FakeJsonRpc:
        local_port = 12345

        def __init__(self, *args):
            self.args = args

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def call(self, method, params):
            calls.append((method, params["addonid"]))
            return {"addon": {"version": versions[params["addonid"]]}}

    monkeypatch.setattr(
        "tools.certify_device_matrix.AdbJsonRpcClient",
        FakeJsonRpc,
    )
    monkeypatch.setattr(
        "tools.certify_device_matrix._recover_kodi",
        lambda *args: None,
    )
    monkeypatch.setattr(
        "tools.certify_device_matrix.installed_addon_origins",
        lambda *args, **kwargs: {
            "changed": TESTING_ORIGIN,
            "unchanged": "repository.mwodevelop",
        },
    )

    state = _addon_state(
        "adb",
        5038,
        "device",
        expected,
        stable,
    )

    assert state == {
        "versions": versions,
        "origins": {
            "changed": TESTING_ORIGIN,
            "unchanged": "repository.mwodevelop",
        },
    }
    assert [call[1] for call in calls] == ["changed", "unchanged"]


def test_recovery_force_stops_before_starting_kodi(monkeypatch):
    commands = []
    waits = []
    sleeps = []

    monkeypatch.setattr(
        "tools.certify_device_matrix._adb",
        lambda *args: commands.append(args),
    )
    monkeypatch.setattr(
        "tools.certify_device_matrix._wait_for_jsonrpc",
        lambda *args: waits.append(args),
    )
    monkeypatch.setattr(
        "tools.certify_device_matrix.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )

    _recover_kodi("adb", 5038, "device", 12345)

    assert commands == [
        (
            "adb",
            5038,
            "device",
            "shell",
            "am",
            "force-stop",
            "org.xbmc.kodi",
        ),
        (
            "adb",
            5038,
            "device",
            "shell",
            "am",
            "start",
            "-n",
            "org.xbmc.kodi/.Splash",
        ),
    ]
    assert waits == [("127.0.0.1", 12345)]
    assert sleeps == [20]


def test_functional_check_recovers_kodi_once_after_transient_failure(
    monkeypatch, tmp_path
):
    report = tmp_path / "result.json"
    attempts = []
    recoveries = []

    def fake_run(argv, env=None):
        attempts.append((argv, env))
        if len(attempts) == 1:
            raise subprocess.CalledProcessError(
                1,
                argv,
                stderr="failed https://example.invalid/?token=secret",
            )
        report.write_text('{"result":"passed"}\n', encoding="utf-8")

    monkeypatch.setattr("tools.certify_device_matrix._run", fake_run)
    monkeypatch.setattr(
        "tools.certify_device_matrix._recover_kodi",
        lambda *args: recoveries.append(args),
    )

    _run_functional_check(
        "check",
        ["python", "check.py"],
        report,
        {"TEST": "1"},
        "adb",
        5038,
        "device",
        12345,
    )

    assert len(attempts) == 2
    assert len(recoveries) == 1
    assert report.is_file()


def test_functional_check_fails_after_two_attempts(monkeypatch, tmp_path):
    report = tmp_path / "result.json"

    def always_fail(argv, env=None):
        raise subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr("tools.certify_device_matrix._run", always_fail)
    monkeypatch.setattr(
        "tools.certify_device_matrix._recover_kodi",
        lambda *args: None,
    )

    with pytest.raises(RuntimeError, match="2 controlled attempts"):
        _run_functional_check(
            "check",
            ["python", "check.py"],
            report,
            {},
            "adb",
            5038,
            "device",
            12345,
        )


def test_diagnostic_redacts_urls_and_credentials():
    redacted = _redacted_diagnostic(
        "open plugin://addon/path then https://example.invalid/?token=secret"
    )

    assert "plugin://" not in redacted
    assert "https://" not in redacted
    assert "secret" not in redacted
