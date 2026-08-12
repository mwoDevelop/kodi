from tools.build_addon_candidate import build


def test_local_candidate_is_deterministic_and_identified(tmp_path):
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    one = build("script.module.mwoscrapers", first)
    two = build("script.module.mwoscrapers", second)

    assert one["addon_id"] == "script.module.mwoscrapers"
    assert one["version"] == "0.2.0"
    assert one["zip_sha256"] == two["zip_sha256"]
    assert one["files"] == two["files"]
