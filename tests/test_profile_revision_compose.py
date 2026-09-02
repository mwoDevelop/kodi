from tools.profile_revision_compose import compose


def revision(adapters, policy="a"):
    return {
        "schema": 2,
        "revision_id": "sha256:" + "0" * 64,
        "policy_sha256": policy * 64,
        "kodi_major": 21,
        "adapters": adapters,
    }


def test_partial_update_carries_forward_unmodified_active_components():
    favourite = {
        "adapter": "kodi_favourites_v1",
        "apply_mode": "hot_apply",
        "ownership": "whole_document",
        "items": [],
        "artwork": [],
    }
    active = revision(
        {
            "kodi.favourites": favourite,
            "umbrella.preferences": {"values": {"cache.providers": 48}},
        }
    )
    update = revision({"umbrella.preferences": {"values": {"cache.providers": 6}}})

    result = compose(active, update)

    assert result["adapters"]["kodi.favourites"] == favourite
    assert result["adapters"]["umbrella.preferences"] == {
        "values": {"cache.providers": 6}
    }
    assert result["required_capabilities"] == ["portable_favourites_v1"]
    assert result["minimum_client_version"] == "1.0.0"
    assert result["revision_id"].startswith("sha256:")


def test_skin_menu_adds_capability_and_minimum_client():
    menu = {
        "adapter": "skin_shortcuts_v1",
        "apply_mode": "hot_apply",
        "ownership": "whole_document",
        "skin_id": "skin.aeon.nox.silvo",
        "menu_id": "mainmenu",
        "items": [],
    }
    result = compose(
        revision({}),
        revision({}),
        extra_adapters={"kodi.skin_menu": menu},
    )

    assert result["adapters"]["kodi.skin_menu"] == menu
    assert result["required_capabilities"] == ["skin-shortcuts-menu-v1"]
    assert result["minimum_client_version"] == "1.5.0"
