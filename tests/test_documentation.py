import re
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")


def project_documents():
    documents = set(ROOT.glob("*.md"))
    documents.update((ROOT / "docs").rglob("*.md"))
    documents.update((ROOT / "deploy").glob("*/README.md"))
    documents.update((ROOT / "tests" / "e2e").rglob("*.md"))
    return sorted(documents)


def local_targets(document):
    content = document.read_text(encoding="utf-8")
    for match in MARKDOWN_LINK.finditer(content):
        raw = match.group(1).strip().strip("<>")
        target = unquote(raw.split("#", 1)[0])
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        yield raw, (document.parent / target).resolve()


def test_all_project_documentation_links_resolve():
    missing = []
    for document in project_documents():
        for raw, target in local_targets(document):
            if not target.exists():
                missing.append(f"{document.relative_to(ROOT)} -> {raw}")
    assert not missing, "Missing local documentation targets:\n" + "\n".join(missing)


def test_main_readme_exposes_documentation_entry_points():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for target in (
        "docs/README.md",
        "docs/kodi-private-profile.md",
        "docs/qnap-images.md",
        "docs/scheduled-processes.md",
        "tests/e2e/README.md",
        "docs/e2e-results/README.md",
    ):
        assert f"]({target})" in readme


def test_every_project_document_is_reachable_from_main_readme():
    documents = {path.resolve() for path in project_documents()}
    pending = [(ROOT / "README.md").resolve()]
    reachable = set()
    while pending:
        document = pending.pop()
        if document in reachable:
            continue
        reachable.add(document)
        pending.extend(
            target
            for _raw, target in local_targets(document)
            if target in documents and target not in reachable
        )

    missing = sorted(path.relative_to(ROOT) for path in documents - reachable)
    assert not missing, "Documentation not reachable from README.md: " + ", ".join(
        str(path) for path in missing
    )


def test_e2e_index_lists_every_dated_markdown_report():
    results = ROOT / "docs" / "e2e-results"
    index = (results / "README.md").read_text(encoding="utf-8")
    missing = [
        report.name
        for report in sorted(results.glob("*.md"))
        if report.name != "README.md" and f"]({report.name})" not in index
    ]
    assert not missing, "Reports missing from E2E index: " + ", ".join(missing)
