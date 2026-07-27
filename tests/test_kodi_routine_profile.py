import json
from pathlib import Path

import pytest

from tools.kodi_routine_profile import (
    canonical_json,
    digest,
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


def layered_policy(tmp_path):
    document = json.loads(
        Path(POLICY).read_text(encoding="utf-8")
    )
    umbrella = document["scopes"]["routine"]["adapters"][1]["settings"]
    umbrella["sources.useonlyone"] = {
        "type": "boolean",
        "class": "device_overlay",
        "layer": {
            "id": "android-tv",
            "selector": {
                "all_target_tags": ["android-tv:armeabi-v7a"]
            },
        },
    }
    umbrella["rd_cloud.enabled"] = {
        "type": "boolean",
        "class": "device_overlay",
        "layer": {
            "id": "bedroom-tv",
            "selector": {"logical_device_id": "bedroom-tv"},
        },
    }
    path = tmp_path / "layered-policy.json"
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


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


def test_schema_three_exports_portable_base_and_ordered_layers(tmp_path):
    manifest = export_routine_profile(
        profile(tmp_path),
        layered_policy(tmp_path),
        21,
        revision_schema=3,
    )

    assert manifest["schema"] == 3
    assert "adapters" not in manifest
    umbrella = manifest["base"]["adapters"]["umbrella.preferences"]
    assert "sources.useonlyone" not in umbrella["values"]
    assert "rd_cloud.enabled" not in umbrella["values"]
    assert [layer["id"] for layer in manifest["layers"]] == [
        "android-tv",
        "bedroom-tv",
    ]
    assert manifest["layers"][0]["adapters"]["umbrella.preferences"][
        "values"
    ] == {"sources.useonlyone": True}
    assert manifest["layers"][1]["adapters"]["umbrella.preferences"][
        "values"
    ] == {"rd_cloud.enabled": False}
    identity = {
        key: value
        for key, value in manifest.items()
        if key != "revision_id"
    }
    assert manifest["revision_id"] == (
        "sha256:" + digest(canonical_json(identity))
    )


def test_schema_two_exports_only_portable_common_subset(tmp_path):
    manifest = export_routine_profile(
        profile(tmp_path),
        layered_policy(tmp_path),
        21,
        revision_schema=2,
    )

    values = manifest["adapters"]["umbrella.preferences"]["values"]
    assert "sources.useonlyone" not in values
    assert "rd_cloud.enabled" not in values


def test_policy_rejects_unknown_layer_selector(tmp_path):
    path = layered_policy(tmp_path)
    document = json.loads(path.read_text(encoding="utf-8"))
    rule = document["scopes"]["routine"]["adapters"][1]["settings"][
        "sources.useonlyone"
    ]
    rule["layer"]["selector"] = {"platform": "android"}
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="layer selector"):
        load_routine_policy(path)


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
