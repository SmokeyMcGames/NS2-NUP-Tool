"""Round-trip package identities and metadata alongside a complete extraction."""

import json
from pathlib import Path, PurePosixPath

from nup_core import format as F, meta as M
from nup_core.discover import PackInput, _resolve_title_id

SIDECAR = ".ns2-nup"
FORMAT = "NS2 NUP Tool extracted bundle v1"


def package_paths(packages):
    used = set()
    addons = {}
    paths = []
    for index, package in enumerate(packages):
        if package.kind == F.KIND_BASE:
            path = "base"
        elif package.kind == F.KIND_UPDATE:
            path = f"updates/{package.version}"
        elif package.kind == F.KIND_ADDON:
            number = addons.get(package.title_id, 0)
            addons[package.title_id] = number + 1
            path = f"dlc/{package.title_id:016X}/{number}"
        else:
            raise ValueError(f"Unsupported package kind: {package.kind}")
        if path in used:
            path += f"-package-{index}"
        used.add(path)
        paths.append(path)
    return paths


def write_bundle_metadata(root, reader, paths):
    sidecar = root / SIDECAR
    sidecar.mkdir()
    records = []
    for index, (package, path) in enumerate(zip(reader.packages, paths)):
        block = bytes(reader._mm[package.meta_offset:package.meta_offset + package.meta_size])
        (sidecar / f"{index}.meta").write_bytes(block)
        metadata = M.parse_block(block)
        if metadata.get(F.TLV_ICON):
            (sidecar / f"{index}-icon.png").write_bytes(metadata[F.TLV_ICON])
        records.append({"path": path, "kind": package.kind, "title_id": f"{package.title_id:016X}",
                        "version": package.version, "flags": package.flags})
    (sidecar / "manifest.json").write_text(json.dumps({"format": FORMAT, "packages": records}, indent=2), encoding="utf-8")


def read_bundle_packages(source, override=None):
    sidecar = source / SIDECAR
    if not sidecar.exists():
        return None
    if sidecar.is_symlink() or sidecar.is_junction():
        raise ValueError("The extracted-bundle metadata folder must not be a link.")
    manifest = sidecar / "manifest.json"
    if not manifest.is_file() or manifest.is_symlink() or manifest.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("Missing or invalid extracted-bundle manifest.")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("format") != FORMAT or not isinstance(data.get("packages"), list) or not data["packages"]:
        raise ValueError("Unsupported extracted-bundle manifest.")
    packages, roots = [], []
    for index, row in enumerate(data["packages"]):
        relative = PurePosixPath(row["path"])
        if (relative.is_absolute() or not relative.parts or any(p in (".", "..", SIDECAR) or ":" in p or "\\" in p
                                                               for p in relative.parts)):
            raise ValueError("Invalid package path in the extracted-bundle manifest.")
        root = source.joinpath(*relative.parts)
        resolved = root.resolve()
        if (not resolved.is_relative_to(source.resolve()) or resolved == source.resolve()
                or not root.is_dir() or any(resolved == old or resolved in old.parents or old in resolved.parents for old in roots)):
            raise ValueError(f"Missing, overlapping, or unsafe extracted package folder: {relative}")
        roots.append(resolved)
        kind, version, flags = row["kind"], row["version"], row["flags"]
        identity = row["title_id"]
        if (kind not in F.KIND_NAMES or type(version) is not int or not 0 <= version <= 0xFFFFFFFF
                or type(flags) is not int or flags & ~F.PKG_FLAG_STANDALONE_UPDATE
                or not isinstance(identity, str) or len(identity) != 16):
            raise ValueError("Invalid package identity in the extracted-bundle manifest.")
        package = PackInput(kind, str(root), int(identity, 16), version, flags)
        _resolve_title_id(package, override if kind == F.KIND_BASE and override is not None else int(identity, 16))
        meta_path = sidecar / f"{index}.meta"
        if not meta_path.is_file() or meta_path.is_symlink() or meta_path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError(f"Missing or invalid package metadata: {meta_path.name}")
        package.bundle_metadata = meta_path.read_bytes()
        package.bundle_icon = str(sidecar / f"{index}-icon.png")
        packages.append(package)
    return packages


def merge_saved_metadata(package, generated):
    if not hasattr(package, "bundle_metadata"):
        return generated
    saved = M.parse_block(package.bundle_metadata)
    current = M.parse_block(generated)
    # Preserve provenance and opaque/private records while allowing user edits
    # and metadata read from the actual executable to take precedence.
    if F.TLV_SOURCE_DUMP in saved:
        current.pop(F.TLV_SOURCE_DUMP, None)
    if hasattr(package, "launch_content"):
        for tag in (F.TLV_NPDM, F.TLV_BUILD_ID):
            saved.pop(tag, None)
    saved.update(current)
    return M.serialize_block(saved)
