import datetime as dt
import io
import json
import os
import stat
import zipfile
from pathlib import Path

import pytest

from tools.upstream_security_scan import (
    SecurityPolicyError,
    finalize,
    inventory,
    load_policy,
    verify,
)


NOW = "2026-07-30T12:00:00Z"
CLAM_VERSION = "ClamAV 1.5.3/27840/Thu Jul 30 10:00:00 2026"


@pytest.fixture
def policy(tmp_path):
    document = {
        "schema": 1,
        "policy_version": "test-1",
        "images": {
            "clamav": "example.invalid/clamav@sha256:" + "1" * 64,
            "semgrep": "example.invalid/semgrep@sha256:" + "2" * 64,
            "gitleaks": "example.invalid/gitleaks@sha256:" + "3" * 64,
        },
        "limits": {
            "max_files": 32,
            "max_file_bytes": 4096,
            "max_total_bytes": 16384,
            "max_archive_depth": 3,
            "max_compression_ratio": 100,
            "max_path_bytes": 256,
            "scan_timeout_seconds": 30,
        },
        "attestation": {
            "max_age_hours": 24,
            "max_signature_age_hours": 48,
            "clock_skew_seconds": 300,
        },
        "semgrep_config": "security/test.yml",
    }
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return load_policy(path)


def _zip(path, entries):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries:
            archive.writestr(name, payload)


def _reports(tmp_path, scanned_files=1):
    clamav = tmp_path / "clamav.txt"
    clamav.write_text(
        "----------- SCAN SUMMARY -----------\n"
        "Known viruses: 9000000\n"
        "Engine version: 1.5.3\n"
        "Scanned directories: 1\n"
        "Scanned files: %d\n"
        "Infected files: 0\n" % scanned_files,
        encoding="utf-8",
    )
    semgrep = tmp_path / "semgrep.json"
    semgrep.write_text('{"errors":[],"results":[]}\n', encoding="utf-8")
    gitleaks = tmp_path / "gitleaks.json"
    gitleaks.write_text("[]\n", encoding="utf-8")
    return clamav, semgrep, gitleaks


def _clean_report(tmp_path, candidate, policy):
    inv = inventory(candidate, policy, candidate_id="a" * 64)
    clamav, semgrep, gitleaks = _reports(
        tmp_path,
        scanned_files=inv["coverage"]["files"],
    )
    return finalize(
        inv,
        policy,
        clamav,
        0,
        CLAM_VERSION,
        semgrep,
        0,
        gitleaks,
        0,
        scanned_at=NOW,
    )


def test_clean_candidate_is_bound_and_verifiable(tmp_path, policy):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "addon.py").write_text("VALUE = 1\n", encoding="utf-8")
    report = _clean_report(tmp_path, candidate, policy)
    assert report["result"] == "clean"
    destination = tmp_path / "report.json"
    destination.write_text(json.dumps(report), encoding="utf-8")
    verified = verify(
        candidate,
        destination,
        policy,
        candidate_id="a" * 64,
        now="2026-07-30T13:00:00Z",
    )
    assert verified["candidate_id"] == "a" * 64


def test_changed_candidate_invalidates_report(tmp_path, policy):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    target = candidate / "addon.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    report = _clean_report(tmp_path, candidate, policy)
    destination = tmp_path / "report.json"
    destination.write_text(json.dumps(report), encoding="utf-8")
    target.write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(SecurityPolicyError, match="binding differs"):
        verify(
            candidate,
            destination,
            policy,
            candidate_id="a" * 64,
            now="2026-07-30T13:00:00Z",
        )


def test_report_and_signature_expiry_are_fail_closed(tmp_path, policy):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "addon.py").write_text("VALUE = 1\n", encoding="utf-8")
    report = _clean_report(tmp_path, candidate, policy)
    destination = tmp_path / "report.json"
    destination.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(SecurityPolicyError, match="expired"):
        verify(
            candidate,
            destination,
            policy,
            candidate_id="a" * 64,
            now="2026-08-02T13:00:00Z",
        )


@pytest.mark.parametrize(
    "entry",
    (
        "../escape.py",
        "/absolute.py",
    ),
)
def test_archive_traversal_is_rejected(tmp_path, policy, entry):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    _zip(candidate / "addon.zip", [(entry, b"bad")])
    with pytest.raises(SecurityPolicyError, match="path"):
        inventory(candidate, policy)


def test_archive_symlink_is_rejected(tmp_path, policy):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        item = zipfile.ZipInfo("link")
        item.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(item, "target")
    (candidate / "addon.zip").write_bytes(payload.getvalue())
    with pytest.raises(SecurityPolicyError, match="symlink"):
        inventory(candidate, policy)


def test_encrypted_archive_is_rejected(tmp_path, policy, monkeypatch):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    _zip(candidate / "addon.zip", [("addon.py", b"clean")])
    original = zipfile.ZipFile.infolist

    def encrypted(self):
        result = original(self)
        result[0].flag_bits |= 0x1
        return result

    monkeypatch.setattr(zipfile.ZipFile, "infolist", encrypted)
    with pytest.raises(SecurityPolicyError, match="encrypted"):
        inventory(candidate, policy)


def test_candidate_symlink_is_rejected(tmp_path, policy):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("secret", encoding="utf-8")
    (candidate / "link").symlink_to(outside)
    with pytest.raises(SecurityPolicyError, match="special"):
        inventory(candidate, policy)


def test_candidate_root_symlink_is_rejected(tmp_path, policy):
    actual = tmp_path / "actual"
    actual.mkdir()
    link = tmp_path / "candidate"
    link.symlink_to(actual, target_is_directory=True)
    with pytest.raises(SecurityPolicyError, match="root symlink"):
        inventory(link, policy)


def test_external_archive_bytes_are_bound_to_payload(tmp_path, policy):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "addon.py").write_text("VALUE = 1\n", encoding="utf-8")
    archive = tmp_path / "upstream.zip"
    _zip(archive, [("addon.py", b"VALUE = 1\n")])
    first = inventory(candidate, policy, archives=[archive])
    _zip(archive, [("addon.py", b"VALUE = 2\n")])
    second = inventory(candidate, policy, archives=[archive])
    assert first["payload_sha256"] != second["payload_sha256"]
    assert first["external_archives"]["upstream.zip"]["sha256"] != second[
        "external_archives"
    ]["upstream.zip"]["sha256"]


def test_clamav_detection_produces_redacted_finding(tmp_path, policy):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "payload.bin").write_bytes(b"not-the-real-eicar-value")
    inv = inventory(candidate, policy)
    clamav, semgrep, gitleaks = _reports(tmp_path)
    clamav.write_text(
        "/scan/payload.bin: Win.Test.EICAR_HDB-1 FOUND\n"
        "----------- SCAN SUMMARY -----------\n"
        "Scanned files: 1\n"
        "Infected files: 1\n",
        encoding="utf-8",
    )
    report = finalize(
        inv,
        policy,
        clamav,
        1,
        CLAM_VERSION,
        semgrep,
        0,
        gitleaks,
        0,
        scanned_at=NOW,
    )
    assert report["result"] == "detected"
    assert report["findings"] == [
        {
            "engine": "clamav",
            "path": "payload.bin",
            "rule": "Win.Test.EICAR_HDB-1",
        }
    ]


def test_scanner_errors_and_incomplete_coverage_are_fail_closed(tmp_path, policy):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "one").write_text("1", encoding="utf-8")
    (candidate / "two").write_text("2", encoding="utf-8")
    inv = inventory(candidate, policy)
    clamav, semgrep, gitleaks = _reports(tmp_path, scanned_files=1)
    with pytest.raises(SecurityPolicyError, match="cover"):
        finalize(
            inv,
            policy,
            clamav,
            0,
            CLAM_VERSION,
            semgrep,
            0,
            gitleaks,
            0,
            scanned_at=NOW,
        )
    with pytest.raises(SecurityPolicyError, match="scanner failed"):
        finalize(
            inv,
            policy,
            clamav,
            2,
            CLAM_VERSION,
            semgrep,
            0,
            gitleaks,
            0,
            scanned_at=NOW,
        )


def test_semgrep_and_gitleaks_findings_never_expose_secret(tmp_path, policy):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "addon.py").write_text("VALUE = 1\n", encoding="utf-8")
    inv = inventory(candidate, policy)
    clamav, semgrep, gitleaks = _reports(tmp_path)
    semgrep.write_text(
        json.dumps(
            {
                "errors": [],
                "results": [
                    {
                        "check_id": "remote-exec",
                        "path": "/scan/addon.py",
                        "extra": {
                            "metadata": {"mwodevelop_action": "block"},
                            "lines": "do not include me",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    secret = "super-secret-token"
    gitleaks.write_text(
        json.dumps(
            [
                {
                    "RuleID": "generic-api-key",
                    "File": "/scan/settings.py",
                    "Fingerprint": "candidate:1:generic-api-key",
                    "Secret": secret,
                }
            ]
        ),
        encoding="utf-8",
    )
    report = finalize(
        inv,
        policy,
        clamav,
        0,
        CLAM_VERSION,
        semgrep,
        1,
        gitleaks,
        1,
        scanned_at=NOW,
    )
    rendered = json.dumps(report)
    assert report["result"] == "detected"
    assert secret not in rendered
    assert "do not include me" not in rendered


@pytest.mark.parametrize("engine", ("semgrep", "gitleaks"))
def test_malformed_scanner_reports_are_fail_closed(tmp_path, policy, engine):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "addon.py").write_text("VALUE = 1\n", encoding="utf-8")
    inv = inventory(candidate, policy)
    clamav, semgrep, gitleaks = _reports(tmp_path)
    (semgrep if engine == "semgrep" else gitleaks).write_text(
        "not-json\n",
        encoding="utf-8",
    )
    with pytest.raises(SecurityPolicyError, match="report is invalid"):
        finalize(
            inv,
            policy,
            clamav,
            0,
            CLAM_VERSION,
            semgrep,
            0,
            gitleaks,
            0,
            scanned_at=NOW,
        )


def test_manifest_rejects_moving_image_tags(tmp_path):
    document = json.loads(
        Path("manifests/upstream-security.json").read_text(encoding="utf-8")
    )
    document["images"]["clamav"] = "clamav/clamav:latest"
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(SecurityPolicyError, match="immutable"):
        load_policy(path)


def test_freshclam_runs_as_the_pinned_images_unprivileged_account():
    action = Path(
        ".github/actions/upstream-malware-scan/action.yml"
    ).read_text(encoding="utf-8")
    assert "--user 1000:1000" in action
    assert "--user=root" not in action
    assert "--cap-drop ALL" in action
    assert "--security-opt no-new-privileges" in action
