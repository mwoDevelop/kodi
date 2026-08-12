import hashlib
import json

import pytest

from tools import qnap_lock


def lock_document():
    services = {}
    for name, service in qnap_lock.qnap_images.services().items():
        services[name] = {
            "image": service.image + "@sha256:" + "a" * 64,
            "source_repository": service.github_repository,
            "source_commit": "b" * 40,
            "input_sha256": "c" * 64,
            "platforms": list(service.platforms),
            "security_report_sha256": "d" * 64,
            "workflow_run_id": "1234",
        }
    identity = {"schema": 1, "channel": "stable", "services": services}
    candidate = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {**identity, "candidate_id": candidate}


def test_qnap_lock_accepts_complete_content_addressed_approval(tmp_path):
    path = tmp_path / "qnap-stable.json"
    path.write_text(json.dumps(lock_document()))

    assert qnap_lock.load_lock(path)["candidate_id"] == lock_document()["candidate_id"]


def test_qnap_lock_rejects_mutated_digest(tmp_path):
    document = lock_document()
    document["services"]["profile-sync"]["image"] = (
        "ghcr.io/mwodevelop/kodi-profile-sync-server@sha256:" + "e" * 64
    )
    path = tmp_path / "qnap-stable.json"
    path.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="candidate ID"):
        qnap_lock.load_lock(path)


def test_compose_lock_requires_exact_complete_approved_inputs(monkeypatch, tmp_path):
    services = qnap_lock.qnap_images.services()
    monkeypatch.setattr(qnap_lock.qnap_images, "services", lambda: services)
    commits = {name: chr(97 + index) * 40 for index, name in enumerate(services)}
    inputs = {name: chr(100 + index) * 64 for index, name in enumerate(services)}
    monkeypatch.setattr(
        qnap_lock.qnap_images,
        "source_identity",
        lambda service, require_clean=False: {"commit": commits[service.name]},
    )
    monkeypatch.setattr(
        qnap_lock.qnap_images,
        "source_input_sha256",
        lambda service, commit=None: inputs[service.name],
    )
    paths = []
    for name, service in services.items():
        path = tmp_path / (name + ".json")
        path.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "service": name,
                    "image": service.image + "@sha256:" + "a" * 64,
                    "source_repository": service.github_repository,
                    "source_commit": commits[name],
                    "input_sha256": inputs[name],
                    "platforms": list(service.platforms),
                    "security_report_sha256": "f" * 64,
                    "workflow_run_id": "1234",
                }
            )
        )
        paths.append(path)

    document = qnap_lock.compose_lock(paths)

    assert set(document["services"]) == set(services)
    assert len(document["candidate_id"]) == 64
    with pytest.raises(ValueError, match="complete"):
        qnap_lock.compose_lock(paths[:-1])


def test_deploy_can_reconcile_only_selected_stable_service(monkeypatch, tmp_path):
    document = lock_document()
    path = tmp_path / "qnap-stable.json"
    path.write_text(json.dumps(document))
    running = {
        name: {"image": item["image"], "status": "running"}
        for name, item in document["services"].items()
    }
    running["upstream-watchdog"]["image"] = (
        "ghcr.io/mwodevelop/kodi-upstream-watchdog@sha256:" + "e" * 64
    )
    deployments = []

    class Lock:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

    monkeypatch.setattr(qnap_lock, "RemoteLock", Lock)
    monkeypatch.setattr(
        qnap_lock.qnap_images,
        "status",
        lambda *_args, **_kwargs: {
            name: dict(item) for name, item in running.items()
        },
    )

    def deploy(name, image, *_args, **_kwargs):
        deployments.append((name, image))
        running[name]["image"] = image

    monkeypatch.setattr(qnap_lock.qnap_images, "deploy", deploy)

    result = qnap_lock.deploy(
        path, service_names=["upstream-watchdog"]
    )

    assert result["result"] == "DEPLOYED"
    assert result["services"] == {"upstream-watchdog": "DEPLOYED"}
    assert deployments == [
        ("upstream-watchdog", document["services"]["upstream-watchdog"]["image"])
    ]


def test_deploy_rejects_service_outside_stable_lock(tmp_path):
    path = tmp_path / "qnap-stable.json"
    path.write_text(json.dumps(lock_document()))

    with pytest.raises(ValueError, match="unknown QNAP stable services"):
        qnap_lock.deploy(path, service_names=["missing"])
