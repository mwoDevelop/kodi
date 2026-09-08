"""Exercise the generated shell probe, not only mocked health output."""

import ast
import subprocess
from pathlib import Path


def test_missing_gateway_cannot_be_masked_by_present_private_files(tmp_path):
    source = Path("tools/qnap_control_plane_gateway.py").read_text()
    tree = ast.parse(source)
    verify = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "verify")
    call = next(n for n in verify.body if isinstance(n, ast.Assign)
                and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "cgi_state")
    expression = ast.Expression(call.value.args[0])
    command = eval(compile(expression, "<probe>", "eval"), {"NAME": "KodiCPGateway"})
    install = tmp_path / "install"
    private = install / "private"
    private.mkdir(parents=True)
    for name in ("operator-username", "operator-credential", "totp-secret"):
        (private / name).touch(mode=0o600)
    service = install / "KodiCPGateway.sh"
    service.touch(mode=0o755)
    command = command.replace(
        "$(/sbin/getcfg KodiCPGateway Install_Path -d missing -f /etc/config/qpkg.conf)",
        str(install),
    ).replace("/etc/init.d/", str(tmp_path / "init") + "/").replace(
        "/home/httpd/cgi-bin/qpkg/", str(tmp_path / "cgi") + "/"
    )
    result = subprocess.run(["sh", "-c", command], capture_output=True, text=True)
    assert result.returncode != 0
    assert "cgi-ready" not in result.stdout
