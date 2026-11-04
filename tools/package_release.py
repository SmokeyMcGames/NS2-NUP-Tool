"""Assemble a tested portable ZIP, matching source materials, and SHA-256 sums."""

import argparse
import ast
import importlib.metadata
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

from PyInstaller.archive.readers import CArchiveReader
from prepare_dependencies import ROOT, digest


def source_version():
    module = ast.parse((ROOT / "ns2_nup_tool/__init__.py").read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError("No app version found")


def verify_bundle(app):
    executable = app / "NS2 NUP Tool.exe"
    archive = CArchiveReader(str(executable))
    embedded = next(name for name in archive.toc if name.endswith(".pyz"))
    modules = archive.open_embedded_archive(embedded).toc
    if "nup_core" not in modules or any(name == "nup" or name.startswith("nup.") for name in modules):
        raise ValueError("Bundle must contain our backend and no reference implementation")
    if any("nup-0.1.0.dist-info" in str(path) or path.name == "reference" for path in app.rglob("*")):
        raise ValueError("Reference dependency files remain in the bundle")
    if not any((app / "_internal/licenses/dependencies").rglob("*LICENSE*")):
        raise ValueError("Dependency license notices were not collected before building")
    return sorted(modules)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    options = parser.parse_args()
    version = source_version()
    if not re.fullmatch(r"v\d+\.\d+\.\d+", options.tag) or options.tag != f"v{version}":
        raise ValueError("Release tag must exactly match the source version")
    if sys.version_info[:3] != (3, 12, 10):
        raise ValueError("Release runtime must match the pinned Python 3.12.10 source archive")
    for name, expected in (("PySide6-Essentials", "6.12.0"), ("shiboken6", "6.12.0"),
                           ("zstandard", "0.25.0"), ("pyinstaller", "6.22.3")):
        if importlib.metadata.version(name) != expected:
            raise ValueError(f"Release dependency differs from the reviewed version: {name}")
    app = ROOT / "dist/NS2 NUP Tool"
    modules = verify_bundle(app)
    for report in ("gui-smoke.json", "portable-smoke.json"):
        data = json.loads((ROOT / "build" / report).read_text())
        if report == "gui-smoke.json" and data.get("status") != "ok":
            raise ValueError("GUI smoke test did not pass")
        if report == "portable-smoke.json" and (not data.get("checks") or any(c["status"] != "passed" for c in data["checks"])):
            raise ValueError("Packaged operation checks did not pass")
    sources = json.loads((ROOT / "distribution/sources.json").read_text())
    for item in sources:
        path = ROOT / "build/dependency-sources" / item["name"]
        if not path.is_file() or digest(path) != item["sha256"]:
            raise ValueError(f"Missing or mismatched corresponding source: {item['name']}")
    output = ROOT / "release"
    output.mkdir(exist_ok=True)
    # The complete folder is retained so Qt libraries remain separate/replaceable.
    for filename in ("LICENSE", "NOTICE", "README.md", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / filename, app / filename)
    shutil.copytree(ROOT / "docs", app / "docs", dirs_exist_ok=True)
    inventory = [{"path": path.relative_to(app).as_posix(), "size": path.stat().st_size,
                  "sha256": digest(path)} for path in sorted(app.rglob("*")) if path.is_file()]
    manifest = {"app": "NS2 NUP Tool", "version": version, "python": sys.version,
                "backend": "nup_core (original GPL-3.0-only implementation)",
                "reference_implementation_bundled": False, "modules": modules,
                "dependencies": {name: importlib.metadata.version(name) for name in
                                 ("PySide6-Essentials", "shiboken6", "zstandard", "pyinstaller")},
                "corresponding_sources": sources, "files": inventory}
    (output / "BUILD-MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    portable = output / f"NS2-NUP-Tool-{options.tag}-windows-x64.zip"
    with zipfile.ZipFile(portable, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(app.rglob("*")):
            if path.is_file():
                archive.write(path, "NS2 NUP Tool/" + path.relative_to(app).as_posix())
    project_source = output / f"NS2-NUP-Tool-{options.tag}-source.zip"
    subprocess.run(["git", "archive", "--format=zip", f"--prefix=NS2-NUP-Tool-{version}/",
                    "-o", str(project_source), "HEAD"], cwd=ROOT, check=True)
    assets = [portable, project_source, output / "BUILD-MANIFEST.json"]
    for item in sources:
        destination = output / item["name"]
        shutil.copy2(ROOT / "build/dependency-sources" / item["name"], destination)
        assets.append(destination)
    notes = ROOT / "distribution/RELEASE_NOTES.md"
    shutil.copy2(notes, output / "RELEASE_NOTES.md")
    (output / "SHA256SUMS.txt").write_text("".join(f"{digest(path)}  {path.name}\n" for path in assets), encoding="utf-8")
    print(f"Release prepared: {portable.name}; {len(assets)} hashed assets. No reference code bundled.")


if __name__ == "__main__":
    main()
