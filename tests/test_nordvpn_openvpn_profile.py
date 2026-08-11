from tools.nordvpn_openvpn_profile import materialize


def test_materialize_is_private_and_adds_credentials_and_bypass(tmp_path):
    source = tmp_path / "source.ovpn"
    source.write_text(
        "client\nproto tcp\nremote vpn.example 443\nauth-user-pass\n",
        encoding="utf-8",
    )
    output = tmp_path / "private" / "profile.ovpn"

    result = materialize(
        source, output, "service-user", "service-pass", ["192.168.1.0/24"]
    )

    assert result["bypass_cidrs"] == ["192.168.1.0/24"]
    assert output.stat().st_mode & 0o777 == 0o600
    payload = output.read_text(encoding="utf-8")
    assert "route 192.168.1.0 255.255.255.0 net_gateway" in payload
    assert "<auth-user-pass>\nservice-user\nservice-pass\n</auth-user-pass>" in payload
