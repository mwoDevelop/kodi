import json
from pathlib import Path
from zipfile import ZipFile, ZipInfo

import pytest

from tools.kodi_addon_runtime_compatibility import (
    KodiVersion,
    assert_compatible,
    evaluate,
    inspect_archive,
    inspect_directory,
    load_policy,
    policy_digest,
    version_at_least,
)

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "manifests/kodi-addon-runtime-compatibility.json"


def runtime(**overrides):
    value = {
        "platform": "android-emulator",
        "kodi_version": "21.2.0",
        "abis": ["x86_64", "x86"],
        "installed_addons": {},
    }
    value.update(overrides)
    return value


def addon_xml(
    addon_id="plugin.video.test",
    version="1.0.0",
    platforms="all",
    requirements=(),
):
    imports = "".join(
        '<import addon="%s" version="%s"%s/>'
        % (
            dependency,
            minimum,
            ' optional="true"' if optional else "",
        )
        for dependency, minimum, optional in requirements
    )
    return (
        '<addon id="%s" version="%s">'
        "<requires>%s</requires>"
        '<extension point="xbmc.addon.metadata">'
        "<platform>%s</platform>"
        "</extension>"
        "</addon>"
    ) % (addon_id, version, imports, platforms)


def write_zip(path, addon_id="plugin.video.test", xml=None, files=None):
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "%s/addon.xml" % addon_id,
            xml or addon_xml(addon_id=addon_id),
        )
        for name, payload in (files or {}).items():
            archive.writestr("%s/%s" % (addon_id, name), payload)
    return path


def test_kodi_version_uses_kodi_epoch_tilde_and_revision_ordering():
    assert KodiVersion("2:1.0") > KodiVersion("1:99.0")
    assert KodiVersion("1.0~beta2") < KodiVersion("1.0")
    assert KodiVersion("1.0-1") < KodiVersion("1.0-2")
    assert KodiVersion("1.0.10") > KodiVersion("1.0.2")
    assert version_at_least("21.5.9", "21.5.0")


def test_policy_is_strict_and_has_a_stable_digest(tmp_path):
    policy = load_policy(POLICY_PATH)
    assert policy_digest(policy) == policy_digest(
        json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    )
    invalid = {**policy, "unexpected": True}
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(ValueError, match="fields differ"):
        load_policy(invalid_path)


def test_archive_inspection_and_projected_dependency_graph(tmp_path):
    dependency_path = write_zip(
        tmp_path / "dependency.zip",
        addon_id="script.module.test",
        xml=addon_xml(
            addon_id="script.module.test",
            version="2.0.0",
            platforms="android linux",
        ),
    )
    addon_path = write_zip(
        tmp_path / "addon.zip",
        xml=addon_xml(
            requirements=(
                ("xbmc.python", "3.0.0", False),
                ("script.module.test", "2.0.0", False),
                ("script.module.optional", "1.0.0", True),
            )
        ),
    )
    descriptors = [
        inspect_archive(addon_path),
        inspect_archive(dependency_path),
    ]
    report = assert_compatible(descriptors, runtime(), load_policy(POLICY_PATH))
    assert report["status"] == "AUDIT_PASS"
    assert report["order"] == ["script.module.test", "plugin.video.test"]
    assert len(report["graph_sha256"]) == 64


def test_planned_version_overrides_installed_version(tmp_path):
    addon_path = write_zip(
        tmp_path / "addon.zip",
        xml=addon_xml(
            requirements=(("script.module.test", "2.0.0", False),)
        ),
    )
    facts = runtime(
        installed_addons={
            "script.module.test": {"version": "1.0.0", "enabled": True}
        }
    )
    report = assert_compatible(
        [inspect_archive(addon_path)],
        facts,
        load_policy(POLICY_PATH),
        planned_versions={"script.module.test": "2.0.0"},
    )
    dependency = report["checks"][0]["dependencies"][0]
    assert dependency == {
        "id": "script.module.test",
        "source": "planned",
        "status": "PASS",
    }


def test_present_optional_dependency_must_still_satisfy_version(tmp_path):
    addon_path = write_zip(
        tmp_path / "addon.zip",
        xml=addon_xml(
            requirements=(("script.module.optional", "2.0.0", True),)
        ),
    )
    facts = runtime(
        installed_addons={
            "script.module.optional": {"version": "1.0.0", "enabled": True}
        }
    )
    report = evaluate(
        [inspect_archive(addon_path)], facts, load_policy(POLICY_PATH)
    )
    assert report["status"] == "INCOMPATIBLE"
    assert report["reasons"] == ["DEPENDENCY_VERSION_TOO_OLD"]


def test_native_payload_and_unknown_platform_fail_closed(tmp_path):
    native_path = write_zip(
        tmp_path / "native.zip", files={"resources/libaddon.so": b"ELF"}
    )
    native = evaluate(
        [inspect_archive(native_path)], runtime(), load_policy(POLICY_PATH)
    )
    assert "NATIVE_PAYLOAD_UNQUALIFIED" in native["reasons"]

    unknown_path = write_zip(
        tmp_path / "unknown.zip", xml=addon_xml(platforms="android future-os")
    )
    unknown = evaluate(
        [inspect_archive(unknown_path)], runtime(), load_policy(POLICY_PATH)
    )
    assert "UNKNOWN_ADDON_PLATFORM" in unknown["reasons"]


def test_cycle_and_archive_escape_are_rejected(tmp_path):
    first = inspect_archive(
        write_zip(
            tmp_path / "first.zip",
            addon_id="plugin.video.first",
            xml=addon_xml(
                addon_id="plugin.video.first",
                requirements=(("plugin.video.second", "1.0.0", False),),
            ),
        )
    )
    second = inspect_archive(
        write_zip(
            tmp_path / "second.zip",
            addon_id="plugin.video.second",
            xml=addon_xml(
                addon_id="plugin.video.second",
                requirements=(("plugin.video.first", "1.0.0", False),),
            ),
        )
    )
    with pytest.raises(ValueError, match="contains a cycle"):
        evaluate([first, second], runtime(), load_policy(POLICY_PATH))

    unsafe = tmp_path / "unsafe.zip"
    with ZipFile(unsafe, "w") as archive:
        archive.writestr("plugin.video.test/addon.xml", addon_xml())
        archive.writestr("../escape", "unsafe")
    with pytest.raises(ValueError, match="unsafe path"):
        inspect_archive(unsafe)


def test_case_collisions_symlinks_and_dtd_are_rejected(tmp_path):
    collision = tmp_path / "collision.zip"
    with ZipFile(collision, "w") as archive:
        archive.writestr("plugin.video.test/addon.xml", addon_xml())
        archive.writestr("plugin.video.test/File.py", "one")
        archive.writestr("plugin.video.test/file.py", "two")
    with pytest.raises(ValueError, match="duplicate paths"):
        inspect_archive(collision)

    symlink = tmp_path / "symlink.zip"
    with ZipFile(symlink, "w") as archive:
        archive.writestr("plugin.video.test/addon.xml", addon_xml())
        entry = ZipInfo("plugin.video.test/link")
        entry.create_system = 3
        entry.external_attr = 0o120777 << 16
        archive.writestr(entry, "target")
    with pytest.raises(ValueError, match="non-regular entry"):
        inspect_archive(symlink)

    dtd = write_zip(
        tmp_path / "dtd.zip",
        xml='<!DOCTYPE addon [<!ENTITY x "x">]><addon id="plugin.video.test" version="1.0.0"/>',
    )
    with pytest.raises(ValueError, match="forbidden XML"):
        inspect_archive(dtd)


def test_directory_inspection_rejects_symlink(tmp_path):
    addon = tmp_path / "plugin.video.test"
    addon.mkdir()
    (addon / "addon.xml").write_text(addon_xml(), encoding="utf-8")
    (addon / "target").write_text("target", encoding="utf-8")
    (addon / "link").symlink_to("target")
    with pytest.raises(ValueError, match="symlink"):
        inspect_directory(addon)
