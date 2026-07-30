#!/usr/bin/env python3
"""Fail-closed security inventory and scanner attestation for upstream bytes."""

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import hashlib
import io
import json
import os
import re
import stat
import tarfile
import zipfile
from pathlib import Path, PurePosixPath


SCHEMA = 1
SHA256 = re.compile(r"^[0-9a-f]{64}$")
IMAGE = re.compile(r"^[a-z0-9./_-]+@sha256:[0-9a-f]{64}$")
CLAM_VERSION = re.compile(r"^ClamAV ([^/]+)/([^/]+)/(.+)$")
SAFE_VERSION = re.compile(r"^[A-Za-z0-9._+-]{1,64}$")
ARCHIVE_SUFFIXES = (
    ".zip",
    ".tar",
    ".tar.gz",
    ".tgz",
    ".tar.bz2",
    ".tbz2",
    ".tar.xz",
    ".txz",
)


class SecurityPolicyError(ValueError):
    """The candidate or scanner evidence violates the security policy."""


def _canonical(value):
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _sha256(value):
    return hashlib.sha256(value).hexdigest()


def _utc(value):
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise SecurityPolicyError("timestamp has no timezone")
    return parsed.astimezone(dt.timezone.utc)


def _now(value=None):
    if value:
        return _utc(value)
    return dt.datetime.now(dt.timezone.utc)


def _iso(value):
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def load_policy(path):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if set(document) != {
        "schema",
        "policy_version",
        "images",
        "limits",
        "attestation",
        "semgrep_config",
    }:
        raise SecurityPolicyError("security manifest fields differ")
    if document["schema"] != SCHEMA:
        raise SecurityPolicyError("unsupported security manifest schema")
    if not SAFE_VERSION.fullmatch(document["policy_version"]):
        raise SecurityPolicyError("invalid policy version")
    images = document["images"]
    if set(images) != {"clamav", "semgrep", "gitleaks"} or not all(
        isinstance(value, str) and IMAGE.fullmatch(value)
        for value in images.values()
    ):
        raise SecurityPolicyError("scanner images are not immutable")
    limits = document["limits"]
    expected_limits = {
        "max_files",
        "max_file_bytes",
        "max_total_bytes",
        "max_archive_depth",
        "max_compression_ratio",
        "max_path_bytes",
        "scan_timeout_seconds",
    }
    if set(limits) != expected_limits or any(
        not isinstance(value, int) or value <= 0 for value in limits.values()
    ):
        raise SecurityPolicyError("scanner limits are invalid")
    attestation = document["attestation"]
    if set(attestation) != {
        "max_age_hours",
        "max_signature_age_hours",
        "clock_skew_seconds",
    } or any(
        not isinstance(value, int) or value <= 0
        for value in attestation.values()
    ):
        raise SecurityPolicyError("attestation limits are invalid")
    config = PurePosixPath(document["semgrep_config"])
    if config.is_absolute() or ".." in config.parts:
        raise SecurityPolicyError("Semgrep configuration path is unsafe")
    return document


def _safe_path(value, max_bytes):
    if not isinstance(value, str) or not value or "\x00" in value:
        raise SecurityPolicyError("candidate path is invalid")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        path.is_absolute()
        or ".." in path.parts
        or len(normalized.encode("utf-8")) > max_bytes
    ):
        raise SecurityPolicyError("candidate path escapes policy limits")
    return path.as_posix()


def _archive_kind(name):
    lowered = name.lower()
    if lowered.endswith(".zip"):
        return "zip"
    if lowered.endswith(ARCHIVE_SUFFIXES[1:]):
        return "tar"
    return None


class _ArchiveBudget:
    def __init__(self, limits):
        self.limits = limits
        self.files = 0
        self.bytes = 0
        self.archives = 0

    def file(self, size):
        if size < 0 or size > self.limits["max_file_bytes"]:
            raise SecurityPolicyError("archive member exceeds file limit")
        self.files += 1
        self.bytes += size
        if self.files > self.limits["max_files"]:
            raise SecurityPolicyError("archive exceeds file-count limit")
        if self.bytes > self.limits["max_total_bytes"]:
            raise SecurityPolicyError("archive exceeds expanded-size limit")


def _inspect_zip(payload, label, depth, budget):
    if depth > budget.limits["max_archive_depth"]:
        raise SecurityPolicyError("archive nesting exceeds limit")
    budget.archives += 1
    names = set()
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except (OSError, zipfile.BadZipFile) as error:
        raise SecurityPolicyError("ZIP archive is invalid") from error
    with archive:
        for item in archive.infolist():
            relative = _safe_path(
                item.filename,
                budget.limits["max_path_bytes"],
            )
            if relative in names:
                raise SecurityPolicyError("archive contains duplicate paths")
            names.add(relative)
            mode = item.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise SecurityPolicyError("archive symlink is forbidden")
            if item.flag_bits & 0x1:
                raise SecurityPolicyError("encrypted archive is forbidden")
            if item.is_dir():
                continue
            budget.file(item.file_size)
            ratio = item.file_size / max(item.compress_size, 1)
            if ratio > budget.limits["max_compression_ratio"]:
                raise SecurityPolicyError("archive compression ratio exceeds limit")
            kind = _archive_kind(relative)
            if kind:
                nested = archive.read(item)
                _inspect_archive_bytes(
                    nested,
                    "%s!%s" % (label, relative),
                    kind,
                    depth + 1,
                    budget,
                )


def _inspect_tar(payload, label, depth, budget):
    if depth > budget.limits["max_archive_depth"]:
        raise SecurityPolicyError("archive nesting exceeds limit")
    budget.archives += 1
    try:
        archive = tarfile.open(fileobj=io.BytesIO(payload), mode="r:*")
    except (OSError, tarfile.TarError) as error:
        raise SecurityPolicyError("tar archive is invalid") from error
    names = set()
    starting_bytes = budget.bytes
    with archive:
        for item in archive:
            relative = _safe_path(item.name, budget.limits["max_path_bytes"])
            if relative in names:
                raise SecurityPolicyError("archive contains duplicate paths")
            names.add(relative)
            if item.issym() or item.islnk() or item.isdev() or item.isfifo():
                raise SecurityPolicyError("special archive member is forbidden")
            if item.isdir():
                continue
            if not item.isfile():
                raise SecurityPolicyError("unsupported archive member type")
            budget.file(item.size)
            kind = _archive_kind(relative)
            if kind:
                source = archive.extractfile(item)
                if source is None:
                    raise SecurityPolicyError("nested archive could not be read")
                _inspect_archive_bytes(
                    source.read(),
                    "%s!%s" % (label, relative),
                    kind,
                    depth + 1,
                    budget,
                )
    ratio = (budget.bytes - starting_bytes) / max(len(payload), 1)
    if ratio > budget.limits["max_compression_ratio"]:
        raise SecurityPolicyError("archive compression ratio exceeds limit")


def _inspect_archive_bytes(payload, label, kind, depth, budget):
    if len(payload) > budget.limits["max_file_bytes"]:
        raise SecurityPolicyError("nested archive exceeds file limit")
    if kind == "zip":
        _inspect_zip(payload, label, depth, budget)
    elif kind == "tar":
        _inspect_tar(payload, label, depth, budget)
    else:
        raise AssertionError("unknown archive kind")


def inventory(candidate, policy, candidate_id=None, archives=()):
    candidate_input = Path(candidate)
    if candidate_input.is_symlink():
        raise SecurityPolicyError("candidate root symlink is forbidden")
    candidate = candidate_input.resolve()
    if not candidate.is_dir():
        raise SecurityPolicyError("candidate root is not a real directory")
    limits = policy["limits"]
    files = {}
    total = 0
    archive_budget = _ArchiveBudget(limits)
    for root, directories, filenames in os.walk(candidate, followlinks=False):
        root_path = Path(root)
        for name in list(directories):
            path = root_path / name
            if path.is_symlink():
                raise SecurityPolicyError("candidate directory symlink is forbidden")
        for name in filenames:
            path = root_path / name
            relative = _safe_path(
                path.relative_to(candidate).as_posix(),
                limits["max_path_bytes"],
            )
            metadata = path.lstat()
            if not stat.S_ISREG(metadata.st_mode):
                raise SecurityPolicyError("candidate contains a special file")
            if metadata.st_size > limits["max_file_bytes"]:
                raise SecurityPolicyError("candidate file exceeds size limit")
            payload = path.read_bytes()
            total += len(payload)
            if len(files) + 1 > limits["max_files"]:
                raise SecurityPolicyError("candidate exceeds file-count limit")
            if total > limits["max_total_bytes"]:
                raise SecurityPolicyError("candidate exceeds total-size limit")
            files[relative] = {
                "executable": bool(metadata.st_mode & 0o111),
                "sha256": _sha256(payload),
                "size": len(payload),
            }
            kind = _archive_kind(relative)
            if kind:
                _inspect_archive_bytes(
                    payload,
                    relative,
                    kind,
                    1,
                    archive_budget,
                )
    external_archives = {}
    for archive_name in archives:
        archive_input = Path(archive_name)
        if archive_input.is_symlink():
            raise SecurityPolicyError("external archive symlink is forbidden")
        archive_path = archive_input.resolve()
        if not archive_path.is_file():
            raise SecurityPolicyError("external archive is not a real file")
        payload = archive_path.read_bytes()
        kind = _archive_kind(archive_path.name)
        if not kind:
            raise SecurityPolicyError("external archive type is unsupported")
        label = _safe_path(archive_path.name, limits["max_path_bytes"])
        if label in external_archives:
            raise SecurityPolicyError("external archive names are duplicated")
        external_archives[label] = {
            "sha256": _sha256(payload),
            "size": len(payload),
        }
        _inspect_archive_bytes(
            payload,
            label,
            kind,
            1,
            archive_budget,
        )
    identity = {
        "external_archives": external_archives,
        "files": files,
    }
    payload_sha256 = _sha256(_canonical(identity))
    if candidate_id is None:
        descriptor = candidate / "candidate.json"
        if descriptor.is_file():
            value = json.loads(descriptor.read_text(encoding="utf-8")).get(
                "candidate_id"
            )
            candidate_id = value if isinstance(value, str) else None
    candidate_id = candidate_id or payload_sha256
    if not SHA256.fullmatch(candidate_id):
        raise SecurityPolicyError("candidate ID is not SHA-256")
    return {
        "schema": SCHEMA,
        "candidate_id": candidate_id,
        "payload_sha256": payload_sha256,
        "coverage": {
            "archive_expanded_bytes": archive_budget.bytes,
            "archive_members": archive_budget.files,
            "archives": archive_budget.archives,
            "bytes": total,
            "files": len(files),
        },
        "external_archives": external_archives,
        "files": files,
    }


def _clamav_findings(payload):
    findings = []
    for line in payload.splitlines():
        match = re.match(r"^(.+): ([A-Za-z0-9._-]+) FOUND$", line.strip())
        if match:
            path = match.group(1).replace("\\", "/")
            findings.append(
                {
                    "engine": "clamav",
                    "path": path.rsplit("/scan/", 1)[-1].lstrip("/"),
                    "rule": match.group(2),
                }
            )
    return findings


def _semgrep_findings(path):
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SecurityPolicyError("Semgrep report is invalid") from error
    if not isinstance(document, dict):
        raise SecurityPolicyError("Semgrep report is not an object")
    errors = document.get("errors", [])
    if errors:
        raise SecurityPolicyError("Semgrep report contains errors")
    findings = []
    for item in document.get("results", []):
        extra = item.get("extra", {})
        metadata = extra.get("metadata", {})
        action = metadata.get("mwodevelop_action", "security_review")
        if action not in {"block", "security_review", "info"}:
            raise SecurityPolicyError("Semgrep action is invalid")
        findings.append(
            {
                "action": action,
                "engine": "semgrep",
                "path": str(item.get("path", "")).replace("\\", "/").lstrip("/"),
                "rule": str(item.get("check_id", "")),
            }
        )
    return findings


def _gitleaks_findings(path):
    try:
        payload = Path(path).read_text(encoding="utf-8").strip()
        document = json.loads(payload) if payload else []
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SecurityPolicyError("Gitleaks report is invalid") from error
    if not isinstance(document, list):
        raise SecurityPolicyError("Gitleaks report is not a list")
    return [
        {
            "engine": "gitleaks",
            "path": str(item.get("File", "")).replace("\\", "/").lstrip("/"),
            "rule": str(item.get("RuleID", "")),
            "fingerprint": _sha256(
                str(item.get("Fingerprint", "")).encode("utf-8")
            ),
        }
        for item in document
    ]


def _clam_version(value):
    match = CLAM_VERSION.fullmatch(value.strip())
    if not match:
        raise SecurityPolicyError("ClamAV version output is invalid")
    engine, database, raw_date = match.groups()
    if not engine or not database:
        raise SecurityPolicyError("ClamAV version output is incomplete")
    parsed = email.utils.parsedate_to_datetime(raw_date)
    if parsed is None:
        raise SecurityPolicyError("ClamAV database date is invalid")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return engine, database, parsed.astimezone(dt.timezone.utc)


def finalize(
    inventory_document,
    policy,
    clamav_output,
    clamav_exit,
    clamav_version,
    semgrep_report,
    semgrep_exit,
    gitleaks_report,
    gitleaks_exit,
    scanned_at=None,
):
    if inventory_document.get("schema") != SCHEMA:
        raise SecurityPolicyError("inventory schema is unsupported")
    now = _now(scanned_at)
    engine, database, signature_time = _clam_version(clamav_version)
    max_signature_age = dt.timedelta(
        hours=policy["attestation"]["max_signature_age_hours"]
    )
    skew = dt.timedelta(seconds=policy["attestation"]["clock_skew_seconds"])
    if signature_time > now + skew or now - signature_time > max_signature_age:
        raise SecurityPolicyError("ClamAV signature database is stale")
    clam_payload = Path(clamav_output).read_text(
        encoding="utf-8",
        errors="replace",
    )
    clam_findings = _clamav_findings(clam_payload)
    if clamav_exit not in {0, 1}:
        raise SecurityPolicyError("ClamAV scanner failed")
    if clamav_exit == 0 and clam_findings:
        raise SecurityPolicyError("ClamAV result contradicts its findings")
    if clamav_exit == 1 and not clam_findings:
        raise SecurityPolicyError("ClamAV detection has no safe finding")
    if re.search(
        r"(?:Limits exceeded|Heuristics[.]Limits[.]Exceeded|ERROR)",
        clam_payload,
        flags=re.IGNORECASE,
    ):
        raise SecurityPolicyError("ClamAV output reports an incomplete scan")
    scanned = re.search(r"^Scanned files:\s*(\d+)$", clam_payload, re.MULTILINE)
    if not scanned or int(scanned.group(1)) < inventory_document["coverage"]["files"]:
        raise SecurityPolicyError("ClamAV did not cover every candidate file")
    if semgrep_exit not in {0, 1}:
        raise SecurityPolicyError("Semgrep scanner failed")
    semgrep_findings = _semgrep_findings(semgrep_report)
    if semgrep_exit == 1 and not semgrep_findings:
        raise SecurityPolicyError("Semgrep failed without a safe finding")
    if gitleaks_exit not in {0, 1}:
        raise SecurityPolicyError("Gitleaks scanner failed")
    gitleaks_findings = _gitleaks_findings(gitleaks_report)
    if gitleaks_exit == 1 and not gitleaks_findings:
        raise SecurityPolicyError("Gitleaks failed without a safe finding")
    findings = clam_findings + semgrep_findings + gitleaks_findings
    if clam_findings or gitleaks_findings or any(
        item.get("action") == "block" for item in semgrep_findings
    ):
        result = "detected"
    elif any(
        item.get("action") == "security_review" for item in semgrep_findings
    ):
        result = "security_review"
    else:
        result = "clean"
    return {
        "schema": SCHEMA,
        "candidate_id": inventory_document["candidate_id"],
        "payload_sha256": inventory_document["payload_sha256"],
        "policy_version": policy["policy_version"],
        "scanned_at": _iso(now),
        "scanner": {
            "clamav_database": database,
            "clamav_signature_at": _iso(signature_time),
            "clamav_version": engine,
            "images": policy["images"],
        },
        "coverage": {
            **inventory_document["coverage"],
            "skipped": 0,
        },
        "checks": {
            "archive_safety": "pass",
            "clamav": "pass" if not clam_findings else "detected",
            "gitleaks": "pass" if not gitleaks_findings else "detected",
            "semgrep": (
                "pass"
                if not semgrep_findings
                else (
                    "detected"
                    if any(
                        item.get("action") == "block"
                        for item in semgrep_findings
                    )
                    else "security_review"
                )
            ),
        },
        "findings": findings,
        "result": result,
    }


def verify(candidate, report, policy, candidate_id=None, now=None):
    report_document = json.loads(Path(report).read_text(encoding="utf-8"))
    if report_document.get("schema") != SCHEMA:
        raise SecurityPolicyError("security report schema is unsupported")
    if report_document.get("result") != "clean":
        raise SecurityPolicyError("security report is not clean")
    current = inventory(candidate, policy, candidate_id=candidate_id)
    for field in ("candidate_id", "payload_sha256"):
        if report_document.get(field) != current[field]:
            raise SecurityPolicyError("security report candidate binding differs")
    if report_document.get("policy_version") != policy["policy_version"]:
        raise SecurityPolicyError("security report policy version differs")
    scanner = report_document.get("scanner", {})
    if scanner.get("images") != policy["images"]:
        raise SecurityPolicyError("security report scanner images differ")
    current_time = _now(now)
    scanned_at = _utc(report_document["scanned_at"])
    signature_at = _utc(scanner["clamav_signature_at"])
    skew = dt.timedelta(seconds=policy["attestation"]["clock_skew_seconds"])
    if scanned_at > current_time + skew:
        raise SecurityPolicyError("security report is from the future")
    if current_time - scanned_at > dt.timedelta(
        hours=policy["attestation"]["max_age_hours"]
    ):
        raise SecurityPolicyError("security report expired")
    if current_time - signature_at > dt.timedelta(
        hours=policy["attestation"]["max_signature_age_hours"]
    ):
        raise SecurityPolicyError("security report signature database expired")
    if report_document.get("coverage", {}).get("skipped") != 0:
        raise SecurityPolicyError("security report skipped candidate files")
    return report_document


def _write(path, value):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(_canonical(value))


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    inventory_parser = commands.add_parser("inventory")
    inventory_parser.add_argument("--candidate", required=True)
    inventory_parser.add_argument("--candidate-id")
    inventory_parser.add_argument("--archive", action="append", default=[])
    inventory_parser.add_argument("--policy", required=True)
    inventory_parser.add_argument("--output", required=True)

    finalize_parser = commands.add_parser("finalize")
    finalize_parser.add_argument("--inventory", required=True)
    finalize_parser.add_argument("--policy", required=True)
    finalize_parser.add_argument("--clamav-output", required=True)
    finalize_parser.add_argument("--clamav-exit", type=int, required=True)
    finalize_parser.add_argument("--clamav-version", required=True)
    finalize_parser.add_argument("--semgrep-report", required=True)
    finalize_parser.add_argument("--semgrep-exit", type=int, required=True)
    finalize_parser.add_argument("--gitleaks-report", required=True)
    finalize_parser.add_argument("--gitleaks-exit", type=int, required=True)
    finalize_parser.add_argument("--scanned-at")
    finalize_parser.add_argument("--output", required=True)

    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--candidate", required=True)
    verify_parser.add_argument("--candidate-id")
    verify_parser.add_argument("--report", required=True)
    verify_parser.add_argument("--policy", required=True)
    verify_parser.add_argument("--now")

    args = parser.parse_args()
    policy = load_policy(args.policy)
    try:
        if args.command == "inventory":
            result = inventory(
                args.candidate,
                policy,
                candidate_id=args.candidate_id,
                archives=args.archive,
            )
            _write(args.output, result)
        elif args.command == "finalize":
            result = finalize(
                json.loads(Path(args.inventory).read_text(encoding="utf-8")),
                policy,
                args.clamav_output,
                args.clamav_exit,
                args.clamav_version,
                args.semgrep_report,
                args.semgrep_exit,
                args.gitleaks_report,
                args.gitleaks_exit,
                scanned_at=args.scanned_at,
            )
            _write(args.output, result)
            if result["result"] != "clean":
                print(json.dumps(result, indent=2, sort_keys=True))
                return 1
        else:
            result = verify(
                args.candidate,
                args.report,
                policy,
                candidate_id=args.candidate_id,
                now=args.now,
            )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except SecurityPolicyError as error:
        failure = {
            "schema": SCHEMA,
            "result": "scanner_unavailable",
            "error_type": type(error).__name__,
        }
        if args.command == "finalize":
            try:
                source = json.loads(
                    Path(args.inventory).read_text(encoding="utf-8")
                )
                failure.update(
                    {
                        "candidate_id": source.get("candidate_id"),
                        "payload_sha256": source.get("payload_sha256"),
                        "policy_version": policy["policy_version"],
                        "coverage": source.get("coverage"),
                        "findings": [],
                    }
                )
                _write(args.output, failure)
            except (OSError, UnicodeError, json.JSONDecodeError):
                pass
        print(json.dumps(failure, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
