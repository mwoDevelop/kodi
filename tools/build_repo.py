#!/usr/bin/env python3
"""Build a deterministic, complete Kodi repository snapshot."""

import argparse
import fnmatch
import hashlib
import json
import shutil
import subprocess
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).parents[1]
ZIP_TIME = (2020, 1, 1, 0, 0, 0)
EXCLUDED_PARTS = {
    ".git",
    ".github",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    ".venv",
    ".venv-downstream",
    "tests",
}


def load_json(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def git_commit(path):
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
    ).strip()


def selected(relative, patterns):
    value = PurePosixPath(relative).as_posix()
    return any(fnmatch.fnmatch(value, pattern) for pattern in patterns)


def addon_files(source, patterns):
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(source)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if selected(relative, patterns):
            yield path, relative


def write_deterministic_zip(output, root_name, files):
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED, compresslevel=9) as archive:
        for path, relative in files:
            info = ZipInfo((PurePosixPath(root_name) / relative).as_posix(), ZIP_TIME)
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


def parse_addon(path):
    root = ElementTree.parse(path).getroot()
    addon_id = root.attrib["id"]
    version = root.attrib["version"]
    if "/" in addon_id or "/" in version:
        raise ValueError("unsafe add-on identity")
    return root, addon_id, version


def render_addons(addons):
    body = [b'<?xml version="1.0" encoding="UTF-8"?>\n<addons>\n']
    for addon in sorted(addons, key=lambda node: node.attrib["id"]):
        ElementTree.indent(addon, space="  ")
        body.append(ElementTree.tostring(addon, encoding="utf-8"))
        body.append(b"\n")
    body.append(b"</addons>\n")
    return b"".join(body)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_dependency_closure(addons):
    ids = {addon.attrib["id"] for addon in addons}
    platform = {"xbmc.python", "script.module.requests", "plugin.video.youtube"}
    for addon in addons:
        for dependency in addon.findall("./requires/import"):
            dependency_id = dependency.attrib["addon"]
            if dependency.attrib.get("optional") == "true":
                continue
            if dependency_id not in ids and dependency_id not in platform:
                raise ValueError(
                    "%s requires missing %s" % (addon.attrib["id"], dependency_id)
                )


def copy_repository_addon(addon_id, channel_root, output_root):
    source = ROOT / "repository" / addon_id
    addon, parsed_id, version = parse_addon(source / "addon.xml")
    if parsed_id != addon_id:
        raise ValueError("repository directory and id differ")
    zip_name = "%s-%s.zip" % (addon_id, version)
    top_level = output_root / zip_name
    channel_zip = channel_root / addon_id / zip_name
    files = list(addon_files(source, ["*"]))
    write_deterministic_zip(top_level, addon_id, files)
    channel_zip.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(top_level, channel_zip)
    return addon


def build(output):
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents and output.name == "":
        raise ValueError("unsafe output directory")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    components = load_json("manifests/components.json")["components"]
    channels = load_json("manifests/channels.json")["channels"]
    built = {}
    provenance = {"schema": 1, "components": {}}

    for addon_id, config in sorted(components.items()):
        source = ROOT / config["source"]
        actual_commit = git_commit(ROOT / config["source"].split("/")[0])
        if actual_commit != config["commit"]:
            raise ValueError(
                "%s commit drift: expected %s, got %s"
                % (addon_id, config["commit"], actual_commit)
            )
        addon, parsed_id, version = parse_addon(source / "addon.xml")
        if parsed_id != addon_id:
            raise ValueError("component directory and id differ")
        files = list(addon_files(source, config["include"]))
        if not files:
            raise ValueError("component has no files: %s" % addon_id)
        built[addon_id] = (addon, version, files)
        provenance["components"][addon_id] = {
            "repository": config["repository"],
            "commit": actual_commit,
            "version": version,
        }

    for channel, config in sorted(channels.items()):
        channel_root = output / channel / "omega"
        channel_root.mkdir(parents=True)
        addons = [copy_repository_addon(config["repository_addon"], channel_root, output)]
        for addon_id in config["components"]:
            addon, version, files = built[addon_id]
            target = channel_root / addon_id / ("%s-%s.zip" % (addon_id, version))
            write_deterministic_zip(target, addon_id, files)
            addons.append(addon)
        validate_dependency_closure(addons)
        index = render_addons(addons)
        (channel_root / "addons.xml").write_bytes(index)
        (channel_root / "addons.xml.sha256").write_text(
            hashlib.sha256(index).hexdigest() + "\n", encoding="ascii"
        )

    (output / "build-provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest_lines = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "artifact-manifest.sha256":
            manifest_lines.append("%s  %s" % (sha256(path), path.relative_to(output)))
    (output / "artifact-manifest.sha256").write_text(
        "\n".join(manifest_lines) + "\n", encoding="ascii"
    )
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="dist")
    args = parser.parse_args()
    print(build(args.output))


if __name__ == "__main__":
    main()
