import json

import pytest

from tools.kodi_routine_profile import (
    export_routine_profile,
    load_routine_policy,
)


POLICY = "manifests/kodi-profile-policy.json"


def write_settings(path, settings):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = ["<settings version=\"2\">"]
    for setting_id, value in settings.items():
        payload.append(
            "  <setting id=%s>%s</setting>"
            % (json.dumps(setting_id), value)
        )
    payload.append("</settings>")
    path.write_text("\n".join(payload) + "\n", encoding="utf-8")


def profile(tmp_path):
    root = tmp_path / "profile"
    write_settings(
        root / "userdata/guisettings.xml",
        {
            "lookandfeel.skin": "skin.estuary",
            "services.webserverpassword": "must-not-export",
        },
    )
    write_settings(
        root
        / "userdata/addon_data/plugin.video.umbrella/settings.xml",
        {
            "realdebrid.filter.filename": "true",
            "sources.useonlyone": "true",
            "rd_cloud.enabled": "false",
            "cache.providers": "6",
            "scrapers.timeout": "30",
            "realdebridtoken": "must-not-export",
            "unknown.preference": "must-not-export",
        },
    )
    return root


def test_policy_is_default_deny_and_declares_expected_adapters():
    _document, routine = load_routine_policy(POLICY)

    assert routine["default"] == "excluded"
    assert routine["default_profile_only"] is True
    assert [item["id"] for item in routine["adapters"]] == [
        "kodi.core",
        "umbrella.preferences",
    ]


def test_export_is_semantic_typed_and_excludes_secrets(tmp_path):
    manifest = export_routine_profile(profile(tmp_path), POLICY, 21)

    assert manifest["schema"] == 2
    assert manifest["revision_id"].startswith("sha256:")
    core = manifest["adapters"]["kodi.core"]
    umbrella = manifest["adapters"]["umbrella.preferences"]
    assert core["values"] == {"lookandfeel.skin": "skin.estuary"}
    assert umbrella["values"] == {
        "cache.providers": 6,
        "rd_cloud.enabled": False,
        "realdebrid.filter.filename": True,
        "scrapers.timeout": 30,
        "sources.useonlyone": True,
    }
    serialized = json.dumps(manifest)
    assert "realdebridtoken" not in serialized
    assert "must-not-export" not in serialized
    assert "unknown.preference" not in serialized


def test_export_is_deterministic(tmp_path):
    root = profile(tmp_path)

    first = export_routine_profile(root, POLICY, 21)
    second = export_routine_profile(root, POLICY, 21)

    assert first == second


def test_export_rejects_invalid_typed_value(tmp_path):
    root = profile(tmp_path)
    write_settings(
        root
        / "userdata/addon_data/plugin.video.umbrella/settings.xml",
        {"sources.useonlyone": "not-a-boolean"},
    )

    with pytest.raises(ValueError, match="not a boolean"):
        export_routine_profile(root, POLICY, 21)


def test_export_rejects_symlinked_managed_file(tmp_path):
    root = tmp_path / "profile"
    target = tmp_path / "outside.xml"
    write_settings(target, {"lookandfeel.skin": "skin.estuary"})
    managed = root / "userdata/guisettings.xml"
    managed.parent.mkdir(parents=True)
    managed.symlink_to(target)

    with pytest.raises(ValueError, match="cannot be a symlink"):
        export_routine_profile(root, POLICY, 21)
