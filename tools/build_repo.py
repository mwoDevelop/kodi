#!/usr/bin/env python3
"""Build a deterministic, complete Kodi repository snapshot."""

import argparse
import fnmatch
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).parents[1]
COMPONENT_ROOT = Path(os.environ.get("KODI_COMPONENT_ROOT", ROOT))
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
        for payload, relative in files:
            info = ZipInfo((PurePosixPath(root_name) / relative).as_posix(), ZIP_TIME)
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            content = payload.read_bytes() if isinstance(payload, Path) else payload
            archive.writestr(info, content)


def parse_addon(path):
    return parse_addon_payload(Path(path).read_bytes())


def parse_addon_payload(payload):
    root = ElementTree.fromstring(payload)
    addon_id = root.attrib["id"]
    version = root.attrib["version"]
    if "/" in addon_id or "/" in version:
        raise ValueError("unsafe add-on identity")
    return root, addon_id, version


def publish_assets(addon, files, target):
    """Publish metadata assets next to the add-on ZIP, as Kodi expects."""
    content = {
        PurePosixPath(relative).as_posix(): (
            payload.read_bytes() if isinstance(payload, Path) else payload
        )
        for payload, relative in files
    }
    for asset in addon.findall("./extension/assets/*"):
        relative = PurePosixPath((asset.text or "").strip())
        if not relative.parts:
            continue
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("unsafe add-on asset path: %s" % relative)
        key = relative.as_posix()
        if key not in content:
            raise ValueError("missing add-on asset: %s" % relative)
        output_path = target.joinpath(*relative.parts)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(content[key])


def component_files(config, commit):
    source_parts = PurePosixPath(config["source"]).parts
    checkout = COMPONENT_ROOT / source_parts[0]
    prefix = PurePosixPath(*source_parts[1:]).as_posix() if source_parts[1:] else ""
    subprocess.run(
        ["git", "-C", str(checkout), "cat-file", "-e", "%s^{commit}" % commit],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    command = ["git", "-C", str(checkout), "ls-tree", "-r", commit]
    if prefix:
        command.extend(["--", prefix])
    rows = subprocess.check_output(command, text=True).splitlines()
    result = []
    for row in rows:
        metadata, full_path = row.split("\t", 1)
        mode, kind, _object_id = metadata.split()
        if kind != "blob" or mode == "120000":
            continue
        relative = PurePosixPath(full_path)
        if prefix:
            relative = relative.relative_to(PurePosixPath(prefix))
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if not selected(relative, config["include"]):
            continue
        payload = subprocess.check_output(
            ["git", "-C", str(checkout), "show", "%s:%s" % (commit, full_path)]
        )
        result.append((payload, relative))
    if not result:
        raise ValueError("component has no files at %s" % commit)
    return result


def validate_provider_api(files, expected):
    by_name = {PurePosixPath(relative).as_posix(): payload for payload, relative in files}
    payload = by_name.get("lib/mwoscrapers/__init__.py", b"").decode(
        "utf-8", errors="replace"
    )
    match = re.search(r"^PROVIDER_API_VERSION\s*=\s*(\d+)\s*$", payload, re.MULTILINE)
    if not match or int(match.group(1)) != int(expected):
        raise ValueError("MwoScrapers provider API contract drift")


def render_addons(addons):
    body = [b'<?xml version="1.0" encoding="UTF-8"?>\n<addons>\n']
    for addon in sorted(addons, key=lambda node: node.attrib["id"]):
        ElementTree.indent(addon, space="  ")
        body.append(ElementTree.tostring(addon, encoding="utf-8"))
        body.append(b"\n")
    body.append(b"</addons>\n")
    return b"".join(body)


def render_home(catalog):
    cards = []
    for channel in ("stable", "testing"):
        data = catalog[channel]
        repository = data["repository"]
        repository_zip = "%s-%s.zip" % (
            repository["id"],
            repository["version"],
        )
        addon_rows = []
        for addon in data["addons"]:
            addon_zip = "%s-%s.zip" % (addon["id"], addon["version"])
            href = "%s/omega/%s/%s" % (channel, addon["id"], addon_zip)
            addon_rows.append(
                '<li><a href="%s">%s</a><span>%s</span></li>'
                % (
                    html.escape(href, quote=True),
                    html.escape(addon["name"]),
                    html.escape(addon["version"]),
                )
            )
        label = "Stable" if channel == "stable" else "Testing"
        description = (
            "Recommended production channel."
            if channel == "stable"
            else "Pre-release channel for integration testing."
        )
        cards.append(
            """
      <section class="card">
        <p class="eyebrow">%s</p>
        <h2>%s</h2>
        <p>%s</p>
        <a class="button" href="%s">Download repository ZIP</a>
        <ul>%s</ul>
        <a class="index-link" href="%s/omega/addons.xml">View Kodi XML index</a>
      </section>"""
            % (
                html.escape(label),
                html.escape(repository["name"]),
                html.escape(description),
                html.escape(repository_zip, quote=True),
                "".join(addon_rows),
                channel,
            )
        )
    return (
        """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>mwoDevelop Kodi Add-ons</title>
  <style>
    :root { color-scheme: dark; font-family: system-ui, sans-serif; }
    body { margin: 0; background: #0b1220; color: #e5edf8; }
    main { width: min(960px, calc(100%% - 32px)); margin: 0 auto; padding: 64px 0; }
    header { max-width: 700px; margin-bottom: 32px; }
    h1 { margin: 0 0 12px; font-size: clamp(2rem, 6vw, 4rem); }
    h2 { margin: 4px 0 8px; }
    p { color: #aebdd0; line-height: 1.6; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; }
    .card { padding: 24px; border: 1px solid #253552; border-radius: 16px; background: #111b2e; }
    .eyebrow { margin: 0; color: #6dd6ff; font-size: .8rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
    .button { display: inline-block; margin: 10px 0 18px; padding: 11px 16px; border-radius: 9px; background: #1887bd; color: white; font-weight: 700; text-decoration: none; }
    ul { margin: 0 0 18px; padding: 0; list-style: none; border-top: 1px solid #253552; }
    li { display: flex; justify-content: space-between; gap: 16px; padding: 12px 0; border-bottom: 1px solid #253552; }
    li a, .index-link { color: #8edcff; }
    li span { color: #aebdd0; font-variant-numeric: tabular-nums; }
    code { color: #d7e7fb; }
  </style>
</head>
<body>
  <main>
    <header>
      <p class="eyebrow">Kodi 21 Omega</p>
      <h1>mwoDevelop Add-ons</h1>
      <p>Download a repository ZIP, install it with Kodi's <strong>Install from zip file</strong>, then install and update add-ons from the selected channel.</p>
    </header>
    <div class="grid">%s
    </div>
  </main>
</body>
</html>
"""
        % "".join(cards)
    ).encode("utf-8")


def render_repository_source(repository):
    repository_zip = "%s-%s.zip" % (
        repository["id"],
        repository["version"],
    )
    return (
        """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>mwoDevelop Kodi repository</title>
</head>
<body>
  <a href="%s">%s</a>
</body>
</html>
"""
        % (
            html.escape(repository_zip, quote=True),
            html.escape(repository_zip),
        )
    ).encode("utf-8")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_dependency_closure(addons):
    ids = {addon.attrib["id"] for addon in addons}
    platform = {
        "xbmc.python",
        "inputstream.adaptive",
        "plugin.video.youtube",
        "script.module.requests",
        "script.module.six",
    }
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


def build(output, lock_overrides=None):
    requested_output = Path(output)
    if requested_output.is_symlink():
        raise ValueError("output directory cannot be a symlink")
    output = requested_output.resolve()
    filesystem_root = Path(output.anchor)
    if output == filesystem_root or output == ROOT or output in ROOT.parents:
        raise ValueError("unsafe output directory")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    components = load_json("manifests/components.json")["components"]
    channels = load_json("manifests/channels.json")["channels"]
    provenance = {"schema": 2, "channels": {}}
    catalog = {}
    lock_overrides = lock_overrides or {}

    for channel, config in sorted(channels.items()):
        lock = lock_overrides.get(channel) or load_json(config["lock"])
        if lock.get("schema") != 1 or lock.get("channel") != channel:
            raise ValueError("invalid %s channel lock" % channel)
        channel_root = output / channel / "omega"
        channel_root.mkdir(parents=True)
        addons = [copy_repository_addon(config["repository_addon"], channel_root, output)]
        channel_provenance = {"lock": config["lock"], "components": {}}
        for addon_id, pin in sorted(lock["components"].items()):
            if addon_id not in components:
                raise ValueError("unknown component in %s lock: %s" % (channel, addon_id))
            component = components[addon_id]
            commit = pin["commit"]
            files = component_files(component, commit)
            by_name = {
                PurePosixPath(relative).as_posix(): payload
                for payload, relative in files
            }
            if "addon.xml" not in by_name:
                raise ValueError("component has no addon.xml: %s" % addon_id)
            addon, parsed_id, version = parse_addon_payload(by_name["addon.xml"])
            if parsed_id != addon_id:
                raise ValueError("component directory and id differ")
            if version != pin["version"]:
                raise ValueError(
                    "%s version drift: expected %s, got %s"
                    % (addon_id, pin["version"], version)
                )
            if "provider_api" in pin:
                validate_provider_api(files, pin["provider_api"])
            addon_root = channel_root / addon_id
            target = addon_root / ("%s-%s.zip" % (addon_id, version))
            write_deterministic_zip(target, addon_id, files)
            digest = sha256(target)
            expected_digest = pin.get("zip_sha256")
            if expected_digest and digest != expected_digest:
                raise ValueError(
                    "%s ZIP drift: expected %s, got %s"
                    % (addon_id, expected_digest, digest)
                )
            publish_assets(addon, files, addon_root)
            addons.append(addon)
            channel_provenance["components"][addon_id] = {
                "repository": component["repository"],
                "commit": commit,
                "version": version,
                "zip_sha256": digest,
            }
        validate_dependency_closure(addons)
        index = render_addons(addons)
        (channel_root / "addons.xml").write_bytes(index)
        (channel_root / "addons.xml.sha256").write_text(
            hashlib.sha256(index).hexdigest() + "\n", encoding="ascii"
        )
        provenance["channels"][channel] = channel_provenance
        repository_addon_id = config["repository_addon"]
        catalog[channel] = {
            "repository": next(
                {
                    "id": addon.attrib["id"],
                    "name": addon.attrib["name"],
                    "version": addon.attrib["version"],
                }
                for addon in addons
                if addon.attrib["id"] == repository_addon_id
            ),
            "addons": [
                {
                    "id": addon.attrib["id"],
                    "name": addon.attrib["name"],
                    "version": addon.attrib["version"],
                }
                for addon in sorted(addons, key=lambda node: node.attrib["id"])
                if addon.attrib["id"] != repository_addon_id
            ],
        }

    (output / "build-provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "index.html").write_bytes(render_home(catalog))
    source_root = output / "repo"
    source_root.mkdir()
    stable_repository = catalog["stable"]["repository"]
    stable_repository_zip = "%s-%s.zip" % (
        stable_repository["id"],
        stable_repository["version"],
    )
    shutil.copyfile(
        output / stable_repository_zip,
        source_root / stable_repository_zip,
    )
    (source_root / "index.html").write_bytes(
        render_repository_source(stable_repository)
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
