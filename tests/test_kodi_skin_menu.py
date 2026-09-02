import json

import pytest

from tools.kodi_skin_menu import (
    _expected_generated,
    _generated_items,
    _source_items,
    expected_document,
    load_skin_menu,
)


def test_repository_skin_menu_is_the_allowlisted_contract():
    assert load_skin_menu("manifests/kodi-skin-menu.json") == expected_document()


def test_skin_menu_rejects_even_a_signed_arbitrary_action(tmp_path):
    document = expected_document()
    document["items"][0]["action"] = "RunScript(plugin.video.untrusted)"
    path = tmp_path / "menu.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="allow-listed"):
        load_skin_menu(path)


def test_host_canary_parser_matches_the_closed_contract():
    expected = expected_document()["items"]
    source = ["<shortcuts>"]
    generated = ["<includes><include name='skinshortcuts-mainmenu'>"]
    for index, item in enumerate(expected, 1):
        visible = (
            "<visible>%s</visible>" % item["visible"]
            if item.get("visible")
            else ""
        )
        source_item = {**item, "visible": visible}
        source.append(
            "<shortcut><defaultID>{id}</defaultID><label>{label}</label>"
            "<label2>{label2}</label2><icon>{icon}</icon><thumb/>"
            "<action>{action}</action>{visible}</shortcut>".format(**source_item)
        )
        rendered = _expected_generated([item])[0]
        rendered = {**rendered, "visible": visible}
        generated.append(
            "<item id='{index}'><label>{label}</label><label2>{label2}</label2>"
            "<icon>{icon}</icon><onclick condition='String.IsEqual(ListItem.Property(path),"
            "ActivateWindow(1129))'>SetProperty(CustomSelect,search,Home)</onclick>"
            "<onclick>{action}</onclick><property name='path'>{action}</property>"
            "{visible}</item>".format(index=index, **rendered)
        )
    source.append("</shortcuts>")
    generated.append("</include></includes>")

    assert _source_items("".join(source).encode()) == expected
    assert _generated_items("".join(generated).encode()) == _expected_generated(
        expected
    )
