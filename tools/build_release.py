#!/usr/bin/env python3
"""
Build the installable add-in zip, the parameter-dump script zip, and release notes.

    python tools/build_release.py            # -> dist/djr_cutoptimizer-vX.Y.Z.zip
    python tools/build_release.py --check    # only validate versions and the changelog

The add-in zip holds one top-level folder named ``djr_cutoptimizer``, because
Fusion needs the folder, the .py and the .manifest to share a name.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADDIN = "djr_cutoptimizer"
DUMP = "djr_dump_cam_params"

INCLUDE_FILES = [f"{ADDIN}.py", f"{ADDIN}.manifest", f"{ADDIN}.svg", "config.py",
                 "README.md", "CHANGELOG.md", "LICENSE"]
INCLUDE_DIRS = ["commands", "lib", "web"]
EXCLUDE_PARTS = {"__pycache__", ".DS_Store"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}


def read_versions() -> tuple[str, str]:
    manifest = json.loads((ROOT / f"{ADDIN}.manifest").read_text(encoding="utf-8"))
    match = re.search(r"^PLUGIN_VERSION\s*=\s*['\"]([^'\"]+)['\"]",
                      (ROOT / "config.py").read_text(encoding="utf-8"), re.M)
    if not match:
        sys.exit("PLUGIN_VERSION not found in config.py")
    return manifest["version"], match.group(1)


def release_notes(version: str) -> str:
    """A short README for the release page: tools/release_intro.md (summary and screenshots),
    the version's CHANGELOG section as "What's new", then tools/release_install.md (install and
    quick start). {version} is filled in, so the screenshots are pinned to the release's tag."""
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(rf"^## v{re.escape(version)}\b.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not match:
        sys.exit(f"CHANGELOG.md has no '## v{version}' section")
    tools = ROOT / "tools"
    intro = (tools / "release_intro.md").read_text(encoding="utf-8")
    install = (tools / "release_install.md").read_text(encoding="utf-8")
    parts = [intro, f"## What's new in v{version}\n\n" + match.group(1).strip(), install]
    return "\n\n".join(p.replace("{version}", version).strip() for p in parts) + "\n"


def files_under(folder: Path):
    for path in sorted(folder.rglob("*")):
        if path.is_file() and not (EXCLUDE_PARTS & set(path.parts)) and path.suffix not in EXCLUDE_SUFFIXES:
            yield path


def iter_addin_files():
    for name in INCLUDE_FILES:
        path = ROOT / name
        if not path.is_file():
            sys.exit(f"missing {name}")
        yield path
    for folder in INCLUDE_DIRS:
        yield from files_under(ROOT / folder)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="validate versions only")
    parser.add_argument("--tag", help="expected tag, e.g. v0.1.0 (CI passes the pushed tag)")
    args = parser.parse_args()

    manifest_version, config_version = read_versions()
    if manifest_version != config_version:
        sys.exit(f"version mismatch: manifest {manifest_version} vs config.py {config_version}")
    if args.tag and args.tag != f"v{manifest_version}":
        sys.exit(f"tag {args.tag} does not match version v{manifest_version}")
    notes = release_notes(manifest_version)
    for f in ("panel.html", "optimizer.js"):
        if not (ROOT / "web" / f).is_file():
            sys.exit(f"web/{f} is missing; run python tools/sync_web.py")
    if args.check:
        print(f"ok: v{manifest_version}")
        return

    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    zip_path = dist / f"{ADDIN}-v{manifest_version}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in iter_addin_files():
            zf.write(path, f"{ADDIN}/{path.relative_to(ROOT).as_posix()}")
    dump_zip = dist / f"{DUMP}-v{manifest_version}.zip"
    with zipfile.ZipFile(dump_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files_under(ROOT / "scripts" / DUMP):
            zf.write(path, f"{DUMP}/{path.relative_to(ROOT / 'scripts' / DUMP).as_posix()}")
    (dist / "RELEASE_NOTES.md").write_text(notes, encoding="utf-8")
    print(zip_path)
    print(dump_zip)


if __name__ == "__main__":
    main()
