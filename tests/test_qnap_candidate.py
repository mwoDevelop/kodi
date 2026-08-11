import json

from tools import qnap_candidate, qnap_images


def test_prepare_reuses_unchanged_approved_image_without_build(monkeypatch, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    service = qnap_images.Service(
        "example",
        "ghcr.io/mwodevelop/example",
        source,
        qnap_images.Path("Dockerfile"),
        ("linux/amd64",),
        github_repository="mwoDevelop/example",
        input_paths=("Dockerfile",),
    )
    entry = {
        "image": service.image + "@sha256:" + "a" * 64,
        "source_repository": service.github_repository,
        "source_commit": "b" * 40,
        "input_sha256": "c" * 64,
        "platforms": ["linux/amd64"],
        "security_report_sha256": "d" * 64,
        "workflow_run_id": "123",
    }
    monkeypatch.setattr(qnap_candidate.qnap_images, "services", lambda: {"example": service})
    monkeypatch.setattr(
        qnap_candidate.qnap_images,
        "source_identity",
        lambda *_args, **_kwargs: {"commit": "b" * 40},
    )
    monkeypatch.setattr(
        qnap_candidate.qnap_images,
        "source_input_sha256",
        lambda *_args, **_kwargs: "c" * 64,
    )
    monkeypatch.setattr(
        qnap_candidate,
        "_prior_lock",
        lambda _repository: {"services": {"example": entry}},
    )
    monkeypatch.setattr(
        qnap_candidate.qnap_images,
        "build_with_actions",
        lambda _service: (_ for _ in ()).throw(AssertionError("unexpected build")),
    )

    def compose(paths):
        approval = json.loads(paths[0].read_text(encoding="utf-8"))
        assert approval == {"schema": 1, "service": "example", **entry}
        return {
            "schema": 1,
            "channel": "stable",
            "candidate_id": "e" * 64,
            "services": {"example": entry},
        }

    monkeypatch.setattr(qnap_candidate.qnap_lock, "compose_lock", compose)

    result = qnap_candidate.prepare(tmp_path)

    assert result["candidate_id"] == "e" * 64
    assert result["build_runs"] == {"example": "reused"}
    assert result["path"].is_file()
