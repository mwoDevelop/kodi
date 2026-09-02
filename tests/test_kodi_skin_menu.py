import json

import pytest

from tools.kodi_skin_menu import expected_document, load_skin_menu


def test_repository_skin_menu_is_the_allowlisted_contract():
    assert load_skin_menu("manifests/kodi-skin-menu.json") == expected_document()


def test_skin_menu_rejects_even_a_signed_arbitrary_action(tmp_path):
    document = expected_document()
    document["items"][0]["action"] = "RunScript(plugin.video.untrusted)"
    path = tmp_path / "menu.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="allow-listed"):
        load_skin_menu(path)
