import os

import pytest
from cryptography import x509
from cryptography.x509.oid import ExtendedKeyUsageOID

from tools.secret_broker_credentials import initialize


def test_initialize_creates_private_pki_and_master_key(tmp_path):
    root = tmp_path / "broker"
    report = initialize(root)

    assert report["status"] == "created"
    assert len(bytes.fromhex((root / "broker-master-key").read_text().strip())) == 32
    server = x509.load_pem_x509_certificate((root / "tls/server.crt").read_bytes())
    san = server.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    assert san.value.get_values_for_type(x509.DNSName) == ["secret-broker"]
    client = x509.load_pem_x509_certificate(
        (root / "profile-sync/client.crt").read_bytes()
    )
    eku = client.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
    assert ExtendedKeyUsageOID.CLIENT_AUTH in eku.value
    control_plane = x509.load_pem_x509_certificate(
        (root / "control-plane/client.crt").read_bytes()
    )
    control_eku = control_plane.extensions.get_extension_for_class(
        x509.ExtendedKeyUsage
    )
    assert ExtendedKeyUsageOID.CLIENT_AUTH in control_eku.value
    assert all(
        os.stat(path).st_mode & 0o077 == 0
        for path in root.rglob("*")
        if path.is_file()
    )
    with pytest.raises(RuntimeError, match="already exists"):
        initialize(root)
