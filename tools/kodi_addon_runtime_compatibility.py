#!/usr/bin/env python3
"""Fail-closed compatibility evaluation for exact Kodi add-on artifacts."""

from __future__ import annotations

import hashlib
import json
import re
import stat
import xml.etree.ElementTree as ET
from functools import total_ordering
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

SCHEMA = 1
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SAFE_VERSION = re.compile(r"^[A-Za-z0-9.+_@~:-]{1,128}$")
NATIVE_SUFFIXES = {".dll", ".dylib", ".pyd", ".so"}
MAX_FILES = 10_000
MAX_UNCOMPRESSED = 64 * 1024 * 1024
MAX_DIRECTORY_UNCOMPRESSED = 256 * 1024 * 1024
MAX_XML = 2 * 1024 * 1024
MAX_COMPRESSION_RATIO = 500
POLICY_KEYS = {"schema", "runtimes", "platforms", "native_addons"}
PLATFORM_KEYS = {"base", "abi_tokens"}
RUNTIME_KEYS = {"virtual_dependencies"}
NATIVE_RULE_KEYS = {"platforms", "abis"}


def canonical_json(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_version(value):
    if not isinstance(value, str) or not SAFE_VERSION.fullmatch(value):
        raise ValueError("unsupported Kodi add-on version")
    KodiVersion(value)
    return value


@total_ordering
class KodiVersion:
    """Python port of Kodi CAddonVersion's Debian-style comparison."""

    _valid = re.compile(r"^[A-Za-z0-9.+_@~]+$")

    def __init__(self, value):
        if not isinstance(value, str) or not value or len(value) > 128:
            raise ValueError("invalid Kodi add-on version")
        raw = value.casefold()
        epoch_text, separator, remainder = raw.partition(":")
        if separator:
            if not epoch_text.isdigit():
                raise ValueError("invalid Kodi add-on version epoch")
            self.epoch = int(epoch_text)
            raw = remainder
        else:
            self.epoch = 0
        upstream, separator, revision = raw.partition("-")
        if not upstream or not self._valid.fullmatch(upstream):
            raise ValueError("invalid Kodi add-on upstream version")
        if separator and (not revision or not self._valid.fullmatch(revision)):
            raise ValueError("invalid Kodi add-on revision")
        self.upstream = upstream
        self.revision = revision
        self.original = value

    @staticmethod
    def _compare_component(left, right):
        left_index = right_index = 0
        while left_index < len(left) and right_index < len(right):
            while (
                left_index < len(left)
                and right_index < len(right)
                and not left[left_index].isdigit()
                and not right[right_index].isdigit()
            ):
                left_char = left[left_index]
                right_char = right[right_index]
                if left_char != right_char:
                    if left_char == "~":
                        return -1
                    if right_char == "~":
                        return 1
                    return -1 if left_char < right_char else 1
                left_index += 1
                right_index += 1
            if left_index < len(left) and right_index < len(right) and (
                not left[left_index].isdigit() or not right[right_index].isdigit()
            ):
                left_char = left[left_index]
                right_char = right[right_index]
                if left_char == "~":
                    return -1
                if right_char == "~":
                    return 1
                return -1 if left_char.isdigit() else 1
            left_match = re.match(r"\d+", left[left_index:])
            right_match = re.match(r"\d+", right[right_index:])
            left_number = int(left_match.group(0)) if left_match else 0
            right_number = int(right_match.group(0)) if right_match else 0
            if left_number != right_number:
                return -1 if left_number < right_number else 1
            left_index += len(left_match.group(0)) if left_match else 0
            right_index += len(right_match.group(0)) if right_match else 0
        if left_index == len(left) and right_index == len(right):
            return 0
        if left_index < len(left):
            return -1 if left[left_index] == "~" else 1
        return 1 if right[right_index] == "~" else -1

    def __eq__(self, other):
        if not isinstance(other, KodiVersion):
            return NotImplemented
        return (
            self.epoch == other.epoch
            and self._compare_component(self.upstream, other.upstream) == 0
            and self._compare_component(self.revision, other.revision) == 0
        )

    def __lt__(self, other):
        if not isinstance(other, KodiVersion):
            return NotImplemented
        if self.epoch != other.epoch:
            return self.epoch < other.epoch
        upstream = self._compare_component(self.upstream, other.upstream)
        if upstream:
            return upstream < 0
        return self._compare_component(self.revision, other.revision) < 0


def version_at_least(actual, minimum):
    return KodiVersion(actual) >= KodiVersion(minimum)


def load_policy(path):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict) or set(document) != POLICY_KEYS:
        raise ValueError("runtime compatibility policy fields differ")
    if document["schema"] != SCHEMA:
        raise ValueError("unsupported runtime compatibility policy schema")
    runtimes = document["runtimes"]
    if not isinstance(runtimes, dict) or not runtimes:
        raise ValueError("runtime compatibility policy has no runtimes")
    for major, runtime in runtimes.items():
        if not str(major).isdigit() or not isinstance(runtime, dict) or set(runtime) != RUNTIME_KEYS:
            raise ValueError("invalid runtime compatibility entry")
        virtual = runtime["virtual_dependencies"]
        if not isinstance(virtual, dict) or not virtual:
            raise ValueError("runtime virtual dependency catalog is empty")
        for addon_id, version in virtual.items():
            if not SAFE_ID.fullmatch(addon_id):
                raise ValueError("invalid virtual dependency id")
            _validate_version(version)
    platforms = document["platforms"]
    if not isinstance(platforms, dict) or not platforms:
        raise ValueError("runtime platform policy is empty")
    for platform, metadata in platforms.items():
        if platform not in {"android", "android-emulator", "linux-flatpak"} or not isinstance(metadata, dict) or set(metadata) != PLATFORM_KEYS:
            raise ValueError("invalid runtime platform policy")
        if metadata["base"] not in {"android", "linux"}:
            raise ValueError("invalid Kodi platform token")
        abi_tokens = metadata["abi_tokens"]
        if not isinstance(abi_tokens, dict) or not abi_tokens:
            raise ValueError("runtime ABI token catalog is empty")
        if any(
            not isinstance(abi, str)
            or not abi
            or not isinstance(token, str)
            or not token
            for abi, token in abi_tokens.items()
        ):
            raise ValueError("invalid runtime ABI token")
    native = document["native_addons"]
    if not isinstance(native, dict):
        raise TypeError("invalid native add-on policy")
    for addon_id, rule in native.items():
        if not SAFE_ID.fullmatch(addon_id) or not isinstance(rule, dict) or set(rule) != NATIVE_RULE_KEYS:
            raise ValueError("invalid native add-on rule")
        if (
            not isinstance(rule["platforms"], list)
            or not rule["platforms"]
            or len(rule["platforms"]) != len(set(rule["platforms"]))
            or any(item not in {"android", "linux"} for item in rule["platforms"])
            or not isinstance(rule["abis"], list)
            or not rule["abis"]
            or len(rule["abis"]) != len(set(rule["abis"]))
            or any(not isinstance(item, str) or not item for item in rule["abis"])
        ):
            raise ValueError("invalid native add-on qualification")
    return document


def policy_digest(policy):
    return hashlib.sha256(canonical_json(policy)).hexdigest()


def _safe_xml(payload):
    if len(payload) > MAX_XML:
        raise ValueError("addon.xml exceeds size policy")
    lowered = payload.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise ValueError("addon.xml contains forbidden XML declarations")
    try:
        return ET.fromstring(payload.decode("utf-8-sig"))
    except (ET.ParseError, UnicodeDecodeError) as error:
        raise ValueError("addon.xml is invalid") from error


def _descriptor(root, artifact_sha256, native_files):
    addon_id = root.attrib.get("id", "")
    version = root.attrib.get("version", "")
    if not SAFE_ID.fullmatch(addon_id):
        raise ValueError("invalid add-on id")
    _validate_version(version)
    requirements = []
    seen = set()
    for item in root.findall("./requires/import"):
        dependency_id = item.attrib.get("addon", "")
        if not SAFE_ID.fullmatch(dependency_id) or dependency_id in seen:
            raise ValueError("invalid or duplicate add-on dependency")
        seen.add(dependency_id)
        minimum = item.attrib.get("version", "0.0.0")
        _validate_version(minimum)
        optional = item.attrib.get("optional", "false") == "true"
        if item.attrib.get("optional", "false") not in {"true", "false"}:
            raise ValueError("invalid optional dependency flag")
        requirements.append(
            {"id": dependency_id, "minimum_version": minimum, "optional": optional}
        )
    platform_node = root.find("./extension[@point='xbmc.addon.metadata']/platform")
    platforms = (
        sorted(set((platform_node.text or "").split()))
        if platform_node is not None and (platform_node.text or "").strip()
        else ["all"]
    )
    if any(not re.fullmatch(r"[A-Za-z0-9._-]+", item) for item in platforms):
        raise ValueError("invalid add-on platform token")
    return {
        "id": addon_id,
        "version": version,
        "artifact_sha256": artifact_sha256,
        "platforms": platforms,
        "requirements": sorted(requirements, key=lambda item: item["id"]),
        "native_files": sorted(native_files),
    }


def inspect_archive(path, expected_id=None, expected_version=None):
    path = Path(path)
    digest = sha256_file(path)
    names = set()
    folded = set()
    total = 0
    native_files = []
    addon_xml_entries = []
    with ZipFile(path) as archive:
        members = archive.infolist()
        if not members or len(members) > MAX_FILES:
            raise ValueError("add-on ZIP file count exceeds policy")
        for member in members:
            name = member.filename
            if "\\" in name or "\x00" in name:
                raise ValueError("add-on ZIP contains an unsafe filename")
            candidate = PurePosixPath(name)
            if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
                raise ValueError("add-on ZIP contains an unsafe path")
            normalized = candidate.as_posix().rstrip("/")
            folded_name = normalized.casefold()
            if normalized in names or folded_name in folded:
                raise ValueError("add-on ZIP contains duplicate paths")
            names.add(normalized)
            folded.add(folded_name)
            if member.flag_bits & 0x1:
                raise ValueError("add-on ZIP contains an encrypted entry")
            mode = member.external_attr >> 16
            file_type = stat.S_IFMT(mode)
            if stat.S_ISLNK(mode) or file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                raise ValueError("add-on ZIP contains a non-regular entry")
            total += member.file_size
            if total > MAX_UNCOMPRESSED:
                raise ValueError("add-on ZIP exceeds uncompressed size policy")
            if (
                member.file_size > 1024 * 1024
                and member.compress_size > 0
                and member.file_size / member.compress_size > MAX_COMPRESSION_RATIO
            ):
                raise ValueError("add-on ZIP compression ratio exceeds policy")
            if len(candidate.parts) == 2 and candidate.name == "addon.xml":
                addon_xml_entries.append(member)
            if not member.is_dir() and candidate.suffix.casefold() in NATIVE_SUFFIXES:
                native_files.append(candidate.as_posix())
        if len(addon_xml_entries) != 1:
            raise ValueError("add-on ZIP must contain exactly one root addon.xml")
        xml_member = addon_xml_entries[0]
        root = _safe_xml(archive.read(xml_member))
        descriptor = _descriptor(root, digest, native_files)
        if PurePosixPath(xml_member.filename).parts[0] != descriptor["id"]:
            raise ValueError("add-on ZIP root differs from add-on id")
    if expected_id is not None and descriptor["id"] != expected_id:
        raise ValueError("add-on ZIP id differs")
    if expected_version is not None and descriptor["version"] != expected_version:
        raise ValueError("add-on ZIP version differs")
    return descriptor


def inspect_directory(path, expected_id=None, expected_version=None):
    root_path = Path(path)
    if root_path.is_symlink() or not root_path.is_dir():
        raise ValueError("add-on directory is unsafe")
    addon_xml = root_path / "addon.xml"
    if addon_xml.is_symlink() or not addon_xml.is_file():
        raise ValueError("add-on directory has no safe addon.xml")
    names = set()
    folded = set()
    total = 0
    native_files = []
    digest = hashlib.sha256()
    count = 0
    for item in sorted(root_path.rglob("*")):
        if item.is_symlink():
            raise ValueError("add-on directory contains a symlink")
        if item.is_dir():
            continue
        if not item.is_file():
            raise ValueError("add-on directory contains a non-regular entry")
        count += 1
        if count > MAX_FILES:
            raise ValueError("add-on directory file count exceeds policy")
        relative = item.relative_to(root_path).as_posix()
        folded_name = relative.casefold()
        if relative in names or folded_name in folded:
            raise ValueError("add-on directory contains duplicate paths")
        names.add(relative)
        folded.add(folded_name)
        size = item.stat().st_size
        total += size
        if total > MAX_DIRECTORY_UNCOMPRESSED:
            raise ValueError("add-on directory exceeds size policy")
        payload = item.read_bytes()
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(payload).digest())
        if item.suffix.casefold() in NATIVE_SUFFIXES:
            native_files.append(relative)
    descriptor = _descriptor(_safe_xml(addon_xml.read_bytes()), digest.hexdigest(), native_files)
    if root_path.name != descriptor["id"]:
        raise ValueError("add-on directory name differs from add-on id")
    if expected_id is not None and descriptor["id"] != expected_id:
        raise ValueError("add-on directory id differs")
    if expected_version is not None and descriptor["version"] != expected_version:
        raise ValueError("add-on directory version differs")
    return descriptor


def _runtime_context(runtime, policy):
    if not isinstance(runtime, dict) or set(runtime) != {
        "platform", "kodi_version", "abis", "installed_addons"
    }:
        raise ValueError("invalid runtime facts")
    if not isinstance(runtime["kodi_version"], str):
        raise TypeError("invalid Kodi runtime version facts")
    _validate_version(runtime["kodi_version"])
    match = re.match(r"^(\d+)", runtime["kodi_version"])
    if not match or match.group(1) not in policy["runtimes"]:
        return None, ["UNSUPPORTED_KODI_MAJOR"]
    platform = policy["platforms"].get(runtime["platform"])
    if platform is None:
        return None, ["UNSUPPORTED_RUNTIME_PLATFORM"]
    abis = runtime["abis"]
    if not isinstance(abis, list) or not abis or any(not isinstance(item, str) or not item for item in abis):
        raise ValueError("invalid runtime ABI facts")
    tokens = {platform["base"]}
    recognized_abis = []
    for abi in abis:
        token = platform["abi_tokens"].get(abi)
        if token:
            tokens.add(token)
            recognized_abis.append(abi)
    if not recognized_abis:
        return None, ["UNSUPPORTED_RUNTIME_ABI"]
    installed = runtime["installed_addons"]
    if not isinstance(installed, dict) or any(
        not isinstance(addon_id, str)
        or not SAFE_ID.fullmatch(addon_id)
        or not isinstance(metadata, dict)
        or set(metadata) != {"version", "enabled"}
        or not isinstance(metadata["enabled"], bool)
        for addon_id, metadata in installed.items()
    ):
        raise ValueError("invalid installed add-on facts")
    for metadata in installed.values():
        _validate_version(metadata["version"])
    return {
        "major": match.group(1),
        "base_platform": platform["base"],
        "platform_tokens": tokens,
        "recognized_abis": recognized_abis,
    }, []


def _topological_order(descriptors):
    by_id = {item["id"]: item for item in descriptors}
    if len(by_id) != len(descriptors):
        raise ValueError("planned add-on ids are not unique")
    edges = {addon_id: set() for addon_id in by_id}
    for addon_id, descriptor in by_id.items():
        for requirement in descriptor["requirements"]:
            if requirement["id"] in by_id:
                edges[addon_id].add(requirement["id"])
    order = []
    remaining = {key: set(value) for key, value in edges.items()}
    while remaining:
        ready = sorted(key for key, dependencies in remaining.items() if not dependencies)
        if not ready:
            raise ValueError("planned add-on dependency graph contains a cycle")
        order.extend(ready)
        for key in ready:
            remaining.pop(key)
        for dependencies in remaining.values():
            dependencies.difference_update(ready)
    return order


def evaluate(descriptors, runtime, policy, planned_versions=None):
    if not isinstance(descriptors, list) or not descriptors:
        raise ValueError("compatibility evaluation requires add-ons")
    if planned_versions is None:
        planned_versions = {}
    if not isinstance(planned_versions, dict) or any(
        not isinstance(addon_id, str)
        or not SAFE_ID.fullmatch(addon_id)
        or not isinstance(version, str)
        for addon_id, version in planned_versions.items()
    ):
        raise ValueError("invalid planned add-on versions")
    for version in planned_versions.values():
        _validate_version(version)
    context, reasons = _runtime_context(runtime, policy)
    order = _topological_order(descriptors)
    descriptor_versions = {item["id"]: item["version"] for item in descriptors}
    conflicts = {
        addon_id
        for addon_id, version in planned_versions.items()
        if addon_id in descriptor_versions
        and descriptor_versions[addon_id] != version
    }
    if conflicts:
        raise ValueError("planned add-on versions conflict with descriptors")
    planned = {**planned_versions, **descriptor_versions}
    installed = {
        addon_id: metadata["version"]
        for addon_id, metadata in runtime["installed_addons"].items()
        if metadata["enabled"]
    }
    available = {**installed, **planned}
    if context is not None:
        available.update(policy["runtimes"][context["major"]]["virtual_dependencies"])
    checks = []
    for descriptor in sorted(descriptors, key=lambda item: item["id"]):
        addon_reasons = []
        if context is not None:
            declared = set(descriptor["platforms"])
            allowed_platform_tokens = {"all"}
            for platform_policy in policy["platforms"].values():
                allowed_platform_tokens.add(platform_policy["base"])
                allowed_platform_tokens.update(
                    platform_policy["abi_tokens"].values()
                )
            if not declared.issubset(allowed_platform_tokens):
                addon_reasons.append("UNKNOWN_ADDON_PLATFORM")
            elif "all" not in declared and not declared.intersection(context["platform_tokens"]):
                addon_reasons.append("ADDON_PLATFORM_MISMATCH")
            if descriptor["native_files"]:
                native_rule = policy["native_addons"].get(descriptor["id"])
                if not native_rule:
                    addon_reasons.append("NATIVE_PAYLOAD_UNQUALIFIED")
                elif (
                    context["base_platform"] not in native_rule["platforms"]
                    or not set(context["recognized_abis"]).intersection(native_rule["abis"])
                ):
                    addon_reasons.append("NATIVE_PAYLOAD_ABI_MISMATCH")
        dependency_checks = []
        for requirement in descriptor["requirements"]:
            actual = available.get(requirement["id"])
            if actual is None:
                if not requirement["optional"]:
                    addon_reasons.append("MISSING_REQUIRED_DEPENDENCY")
                dependency_checks.append(
                    {"id": requirement["id"], "source": "absent", "status": "OPTIONAL_ABSENT" if requirement["optional"] else "MISSING"}
                )
                continue
            source = (
                "virtual"
                if context is not None and requirement["id"] in policy["runtimes"][context["major"]]["virtual_dependencies"]
                else "planned" if requirement["id"] in planned else "installed"
            )
            compatible = version_at_least(actual, requirement["minimum_version"])
            if not compatible:
                addon_reasons.append("DEPENDENCY_VERSION_TOO_OLD")
            dependency_checks.append(
                {"id": requirement["id"], "source": source, "status": "PASS" if compatible else "TOO_OLD"}
            )
        checks.append(
            {"id": descriptor["id"], "status": "PASS" if not addon_reasons else "INCOMPATIBLE", "reasons": sorted(set(addon_reasons)), "dependencies": dependency_checks}
        )
        reasons.extend(addon_reasons)
    graph_document = {
        "addons": [
            {"id": item["id"], "version": item["version"], "sha256": item["artifact_sha256"]}
            for item in sorted(descriptors, key=lambda item: item["id"])
        ],
        "external_planned_versions": {
            addon_id: version
            for addon_id, version in sorted(planned_versions.items())
            if addon_id not in descriptor_versions
        },
        "order": order,
    }
    return {
        "schema": SCHEMA,
        "status": "AUDIT_PASS" if not reasons else "INCOMPATIBLE",
        "policy_sha256": policy_digest(policy),
        "graph_sha256": hashlib.sha256(canonical_json(graph_document)).hexdigest(),
        "runtime": {
            "platform": runtime["platform"],
            "kodi_version": runtime["kodi_version"],
            "abis": sorted(runtime["abis"]),
        },
        "order": order,
        "checks": checks,
        "reasons": sorted(set(reasons)),
    }


def assert_compatible(descriptors, runtime, policy, planned_versions=None):
    report = evaluate(
        descriptors,
        runtime,
        policy,
        planned_versions=planned_versions,
    )
    if report["status"] != "AUDIT_PASS":
        raise RuntimeError(
            "Kodi add-on runtime compatibility failed: %s"
            % ",".join(report["reasons"])
        )
    return report
