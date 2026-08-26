from pathlib import Path

import pytest

from tools.qnap_control_plane_gateway import (
    BACKEND_PORT,
    NAME,
    PROXY_PATH,
    QDK_SHA256,
    VERSION,
    ensure_proxy,
    validate_source,
)


@pytest.fixture
def repository_root():
    return Path(__file__).resolve().parents[1]


def test_gateway_source_is_minimal_and_fail_closed(repository_root):
    assert validate_source(repository_root) == {
        "name": NAME,
        "version": VERSION,
        "backend_port": BACKEND_PORT,
        "proxy_path": PROXY_PATH,
    }
    assert len(QDK_SHA256) == 64
    int(QDK_SHA256, 16)


def test_gateway_webui_uses_canonical_shortcut_path(repository_root):
    config = (
        repository_root / "deploy/qnap-control-plane-gateway/qpkg.cfg"
    ).read_text(encoding="utf-8")
    assert 'QPKG_WEBUI="/control-plane"' in config
    assert 'QPKG_WEBUI="/control-plane/"' not in config


def test_gateway_contains_no_credentials_or_generated_package(repository_root):
    root = repository_root / "deploy/qnap-control-plane-gateway"
    assert not list(root.rglob("*.qpkg"))
    text = "\n".join(
        path.read_text(encoding="utf-8") for path in root.rglob("*") if path.is_file()
    ).lower()
    assert "github_token" not in text
    assert "password=" not in text


def test_gateway_reenables_qpkg_and_refreshes_stale_qts_proxy():
    class Session:
        def __init__(self):
            self.command = None

        def execute(self, command, timeout=None):
            self.command = command
            assert timeout == 90
            return "421"

    session = Session()

    assert ensure_proxy(session) == {
        "proxy_rule": "active",
        "proxy_http_status": 421,
    }
    assert "/sbin/qpkg_cli --enable KodiCPGateway" in session.command
    assert "grep -Fx" in session.command
    assert "/etc/init.d/Qthttpd.sh restart" in session.command
    assert "case \"$code\" in 200|302|303|401|403|421" in session.command
