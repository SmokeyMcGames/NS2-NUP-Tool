"""Conversion operations, independent of the desktop widgets."""

from __future__ import annotations

import base64
import hashlib
import itertools
import os
import re
import shutil
import tempfile
from pathlib import Path

from nup_core import format as F, meta as M
from nup_core.access import app_meta, build_id, localized_icons, localized_titles, resolve_path
from nup_core.verify import verify as core_verify

from .streaming import copy_bytes, open_container, pack_streamed, read_payload
from .dump_metadata import discover_metadata
from .discovery import VERSION_FALLBACK_WARNING, correct_update_layout, discover_packages
from .launch import has_launch_policy, launch_plan, replace_base_from_update, replaces_base_content
from .bundle import package_paths, write_bundle_metadata


class Cancelled(Exception):
    pass


def require_path(value, *, directory=False):
    if not value or not str(value).strip():
        raise ValueError("Choose a folder." if directory else "Choose a file.")
    path = Path(value).expanduser().resolve()
    if not (path.is_dir() if directory else path.is_file()):
        raise ValueError(f"{'Folder' if directory else 'File'} does not exist: {path}")
    return path


def new_output(value, source=None):
    if not value or not str(value).strip():
        raise ValueError("Choose an output path.")
    path = Path(value).expanduser().resolve()
    if path.exists():
        raise ValueError(f"The output already exists. Choose a new name: {path}")
    if not path.parent.is_dir():
        raise ValueError("The output's parent folder must already exist.")
    if source is not None and (path == source or source in path.parents):
        raise ValueError("Choose an output outside the source dump folder.")
    return path


def title_id(value):
    if not value:
        return None
    if not re.fullmatch(r"[0-9a-fA-F]{16}", value):
        raise ValueError("Title ID must be exactly 16 hexadecimal digits.")
    return int(value, 16)


def validate_metadata(options, *, editing=False):
    for field in ("lang_names", "lang_icons"):
        for lang, value in options.get(field, {}).items():
            if not re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", lang) or len(lang) > 255:
                raise ValueError(f"Invalid language tag: {lang!r}. Use a tag such as en or ja.")
            if not editing and not value:
                raise ValueError(f"The value for {lang} cannot be empty when packing.")
    icons = list(options.get("lang_icons", {}).values()) + [options.get("icon")]
    for icon in icons:
        if icon:
            path = require_path(icon)
            if path.stat().st_size > 32 * 1024 * 1024:
                raise ValueError(f"Icon is larger than 32 MiB: {path}")


def scan_dump(request, check, report):
    source = require_path(request.get("source"), directory=True)
    override = title_id(request.get("title_id", ""))
    keep = request.get("keep_listings", False)
    packages = discover_packages(source, override, request.get("update_version", ""), keep_listings=keep)
    result = {"packages": [], "warnings": [], "layout_repairs": [], "size": 0, "files": 0, "largest": 0}
    for package in packages:
        check()
        root = Path(package.src)
        if root.is_symlink() or root.is_junction():
            raise ValueError(f"Linked package folders are not supported: {root}")
        if not hasattr(package, "bundle_metadata") and not any((root / name).is_dir() for name in ("exefs", "romfs")):
            raise ValueError(f"Package has no exefs or romfs folder: {root}")
        if not 0 <= package.version <= 0xFFFFFFFF:
            raise ValueError(f"Update version exceeds the 32-bit format limit: {package.version}")
        count = size = 0
        def walk_error(error):
            raise error
        walks = [os.walk(root, onerror=walk_error, followlinks=False)]
        for loose in getattr(package, "loose_content", []):
            path = Path(loose)
            if path.is_symlink() or path.is_junction():
                raise ValueError(f"Linked dump content is not supported: {path}")
            walks.append(os.walk(path, onerror=walk_error, followlinks=False) if path.is_dir()
                         else iter([(str(path.parent), [], [path.name])]))
        for parent, dirs, files in itertools.chain.from_iterable(walks):
            check()
            for name in dirs + files:
                entry = Path(parent) / name
                if entry.is_symlink() or entry.is_junction():
                    raise ValueError(f"Linked files and folders are not supported: {entry}")
            for name in files:
                if name == ".listing" and not keep:
                    continue
                length = (Path(parent) / name).stat().st_size
                count += 1
                size += length
                result["largest"] = max(result["largest"], length)
            report(0, 0, f"Scanning {root.name} · {count:,} files")
        result["files"] += count
        result["size"] += size
        result["packages"].append({
            "kind": F.KIND_NAMES[package.kind], "title_id": f"{package.title_id:016X}",
            "version": package.version,
            "version_defaulted": package.kind == F.KIND_UPDATE and package.version == 0,
            "flat_update": getattr(package, "flat_update", False), "standalone": bool(package.flags & 1),
            "files": count, "size": size, "source": str(root),
            "build_id": package.build_id.hex().upper() if package.build_id else "",
        })
        if package.title_id == 0:
            result["warnings"].append(f"{root.name}: title ID is unknown (zero). Supply an override if needed.")
        if not count:
            result["warnings"].append(f"{root.name}: this package contains no files.")
        if package.kind == F.KIND_UPDATE and package.version == 0:
            result["warnings"].append(VERSION_FALLBACK_WARNING)
        if getattr(package, "flat_update", False):
            result["layout_repairs"].append(
                f"Create NUP will fix this dump: move all content in updates/ into updates/{package.version}/. "
                "The change is kept after success and undone if packing fails or is cancelled."
            )
    result["unassigned_content"] = [name for p in packages for name in getattr(p, "unassigned_content", [])]
    for name in result["unassigned_content"]:
        result["warnings"].append(f"Unrecognized update/DLC content: {name}. Correct its package folder before creating a NUP.")
    for package in packages:
        for loose in getattr(package, "loose_content", []):
            result["warnings"].append(f"Include loose dump content in {F.KIND_NAMES[package.kind]}: {Path(loose).name}")
    if not result["files"] and not any(hasattr(p, "bundle_metadata") for p in packages):
        raise ValueError("No files were found in the recognized packages.")
    result["metadata"] = discover_metadata(source, packages, check)
    result["version_defaulted"] = any(p.kind == F.KIND_UPDATE and p.version == 0 for p in packages)
    result["update_executable"] = launch_plan(packages)
    return result


def validate_structure(path):
    with open_container(path) as reader:
        if not reader.packages:
            raise ValueError("The container has no packages.")
        if any(cid >= reader.dir_count + reader.file_count for cid in reader.children):
            raise ValueError("A child node points outside the container's node tables.")
    ok, problems = core_verify(str(path), deep=False)
    if not ok:
        raise ValueError("Container structure is invalid:\n" + "\n".join(problems[:20]))


def verify_container(path, deep, check, report, max_problems=20):
    validate_structure(path)
    problems = []
    problem_count = 0
    if deep:
        with open_container(path) as reader:
            for index, entry in enumerate(reader.files):
                check()
                label = entry[0].decode("utf-8", "replace")
                try:
                    read_payload(reader, index, check, report=lambda done, total:
                                 report(index, reader.file_count, f"Hashing {label} · {done:,} bytes"))
                except (ValueError, OSError, F.NupError) as error:
                    problem_count += 1
                    if len(problems) < max_problems:
                        problems.append(str(error))
                report(index + 1, reader.file_count, f"Verified {label}")
    return {"ok": problem_count == 0, "problems": problems, "problem_count": problem_count,
            "mode": "Full SHA-256" if deep else "Structure + TOC hash"}


def publish_file(temporary, output):
    # Linking is atomic and fails if another process has created the destination.
    if os.name == "nt":
        # Windows also supports this on output volumes without hard links (exFAT).
        os.rename(temporary, output)
    else:
        os.link(temporary, output)
        Path(temporary).unlink()


def pack_dump(request, check, report):
    source = require_path(request.get("source"), directory=True)
    output = new_output(request.get("output"), source)
    if output.suffix.lower() != ".nup":
        raise ValueError("Use the .nup extension for the output file.")
    validate_metadata(request)
    level = int(request.get("level", 3))
    if not -5 <= level <= 22:
        raise ValueError("Compression level must be between -5 and 22.")
    preview = scan_dump(request, check, report)
    if preview["unassigned_content"]:
        raise ValueError("Some update/DLC files cannot be assigned to a package; nothing was packed. "
                         "Correct these folders and scan again:\n" + "\n".join(preview["unassigned_content"]))
    if request.get("prefer_update_executable") and not preview["update_executable"]["available"]:
        raise ValueError(preview["update_executable"]["reason"])
    if shutil.disk_usage(output.parent).free < preview["size"] + preview["largest"] + 16 * 1024 * 1024:
        raise ValueError("Insufficient free space for conservative output plus one temporary file. "
                         "Choose a drive with more space.")
    names = dict(request.get("lang_names", {}))
    icons = dict(request.get("lang_icons", {}))
    if request.get("name"):
        names[None] = request["name"]
    if request.get("icon"):
        icons[None] = request["icon"]
    flat_update = next((p for p in preview["packages"] if p["flat_update"]), None)
    check()
    if flat_update:
        report(0, 0, f"Fixing dump folders: updates/ → updates/{flat_update['version']}/")
    with tempfile.TemporaryDirectory(prefix=".ns2-nup-tool-", dir=output.parent) as staging, \
            correct_update_layout(source, flat_update):
        temporary = Path(staging) / "package.nup"
        if flat_update:
            # Locally discovered artwork may have moved with the update payload.
            old_root = source / "updates"
            new_root = old_root / str(flat_update["version"])
            icons = {lang: str(new_root / Path(path).resolve().relative_to(old_root))
                     if Path(path).resolve().is_relative_to(old_root) else path
                     for lang, path in icons.items()}
        packages = discover_packages(source, title_id(request.get("title_id", "")), request.get("update_version", ""),
                                     keep_listings=request.get("keep_listings", False))
        launch = replace_base_from_update(packages) if request.get("prefer_update_executable") else None
        pack_streamed(temporary, source, check=check, report=report, packages=packages,
                      level=level, keep_listings=request.get("keep_listings", False),
                      base_title_id=title_id(request.get("title_id", "")), names=names,
                      icons=icons, publisher=request.get("publisher") or None,
                      display_version=request.get("display_version") or preview["metadata"]["values"]["display_version"])
        check()
        report(0, 0, "Checking the completed container…")
        verification = verify_container(temporary, request.get("verify_after", True), check, report)
        if not verification["ok"]:
            raise ValueError("Output verification failed: " + "\n".join(verification["problems"]))
        check()
        publish_file(temporary, output)
    return {"output": str(output), "size": output.stat().st_size,
            "packages": len(preview["packages"]), "verification": verification,
            "layout_corrected": str(source / "updates" / str(flat_update["version"])) if flat_update else "",
            "preferred_update_executable": launch,
            "warnings": preview["warnings"]}


def inspect_container(request, check, report):
    path = require_path(request.get("file"))
    validate_structure(path)
    with open_container(path) as reader:
        packages = []
        for package in reader.packages:
            check()
            meta = app_meta(reader, package)
            text = lambda tag: meta.get(tag, b"").decode("utf-8", "replace")
            icon = meta.get(F.TLV_ICON, b"")
            packages.append({
                "index": package.index, "kind": package.kind_name,
                "title_id": f"{package.title_id:016X}", "version": package.version,
                "version_str": package.version_str, "standalone": bool(package.flags & 1),
                "prefer_update_executable": has_launch_policy(meta),
                "replace_base_content": replaces_base_content(meta),
                "name": text(F.TLV_TITLE_NAME), "publisher": text(F.TLV_PUBLISHER),
                "display_version": text(F.TLV_DISPLAY_VERSION),
                "source_dump": text(F.TLV_SOURCE_DUMP), "root": package.root_dir,
                "build_id": (build_id(reader, package) or b"").hex().upper(),
                "lang_names": {k.decode("ascii"): v.decode("utf-8", "replace")
                               for k, v in localized_titles(reader, package).items()},
                "lang_icons": [k.decode("ascii") for k in localized_icons(reader, package)],
                "icon": base64.b64encode(icon).decode("ascii") if len(icon) <= 4 * 1024 * 1024 else "",
                "icon_size": len(icon),
            })
        return {"path": str(path), "size": reader.super["file_size"],
                "uuid": reader.super["uuid"].hex(), "packages": packages,
                "dirs": [[name.decode("utf-8", "replace"), first, count]
                         for name, first, count in reader.dirs],
                "files": [[name.decode("utf-8", "replace"), size,
                           "zstd" if codec else "raw", extent_size, sha.hex()]
                          for name, size, sha, offset, extent_size, codec in reader.files],
                "children": reader.children}


def safe_name(raw):
    name = raw.decode("utf-8", "strict")
    if (not name or name in (".", "..") or any(c in name for c in '/\\:<>"|?*')
            or any(ord(c) < 32 for c in name) or name.endswith((" ", "."))
            or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", name)):
        raise ValueError(f"Cannot safely extract this filename on Windows: {name!r}")
    return name


def extract_directory(reader, directory, root, check, report):
    stack = [(directory, root)]
    visited = set()
    count = 0
    while stack:
        check()
        directory, target = stack.pop()
        if directory in visited:
            raise ValueError("A directory is referenced more than once in this extraction tree.")
        visited.add(directory)
        _, first, child_count = reader.dirs[directory]
        names = set()
        for child in reader.children[first:first + child_count]:
            check()
            is_dir = child < reader.dir_count
            node = reader.dirs[child] if is_dir else reader.files[child - reader.dir_count]
            name = safe_name(node[0])
            if name.casefold() in names:
                raise ValueError(f"Case-insensitive filename collision: {name}")
            names.add(name.casefold())
            output = target / name
            if is_dir:
                output.mkdir()
                stack.append((child, output))
            else:
                with output.open("xb") as file:
                    read_payload(reader, child - reader.dir_count, check, target=file,
                                 report=lambda done, total: report(0, 0,
                                     f"Extracting {name} · {done:,} / {total:,} bytes"))
                count += 1
                report(0, 0, f"Extracted {count:,} files in package")
    return count


def extract_container(request, check, report):
    path = require_path(request.get("file"))
    original_stamp = file_stamp(path)
    destination = new_output(request.get("output"))
    # Explicit package/subtree requests remain compatible with older workers.
    scope = request.get("scope", "package" if "package" in request or request.get("subtree") else "all")
    if scope not in ("all", "package"):
        raise ValueError("Choose entire NUP or selected package extraction.")
    if scope == "all" and request.get("subtree"):
        raise ValueError("Subtree extraction is only available for one selected package.")
    validate_structure(path)
    with tempfile.TemporaryDirectory(prefix=".nup-extract-", dir=destination.parent) as staging:
        root = Path(staging) / "contents"
        root.mkdir()
        with open_container(path) as reader:
            if scope == "all":
                required = sum(row[1] for row in reader.files) + sum(p.meta_size * 2 for p in reader.packages)
                if shutil.disk_usage(destination.parent).free < required + 16 * 1024 * 1024:
                    raise ValueError("Insufficient free space for the complete uncompressed NUP.")
                paths = package_paths(reader.packages)
                count = 0
                for package, relative in zip(reader.packages, paths):
                    target = root / relative
                    target.mkdir(parents=True)
                    report(package.index, len(paths), f"Extracting {relative}…")
                    count += extract_directory(reader, package.root_dir, target, check, report)
                write_bundle_metadata(root, reader, paths)
                package_count = len(paths)
            else:
                index = int(request.get("package", 0))
                if not 0 <= index < len(reader.packages):
                    raise ValueError("Select a valid package index.")
                subtree = request.get("subtree", "").replace("\\", "/").strip("/")
                ref = resolve_path(reader, reader.packages[index], subtree)
                if ref is None or not ref.is_dir:
                    raise ValueError("Choose a directory subtree such as exefs, romfs, or romfs/data.")
                count = extract_directory(reader, ref.index, root, check, report)
                package_count = 1
        check()
        if file_stamp(path) != original_stamp:
            raise ValueError("The input NUP changed during extraction; no output was published.")
        os.rename(root, destination)
    return {"output": str(destination), "files": count, "packages": package_count, "scope": scope}


def file_stamp(path):
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, stat.st_ino


def edit_container(request, check, report):
    path = require_path(request.get("file"))
    inplace = request.get("inplace", False)
    output = path if inplace else new_output(request.get("output"))
    validate_metadata(request, editing=True)
    validate_structure(path)
    original_stamp = file_stamp(path)
    fields = ("name", "publisher", "display_version", "icon", "lang_names", "lang_icons",
              "clear_name", "clear_publisher", "clear_display_version", "clear_icon")
    changes = {key: request[key] for key in fields if key in request}
    if not changes:
        raise ValueError("Set or clear at least one metadata field.")
    with tempfile.TemporaryDirectory(prefix=".nup-edit-", dir=output.parent) as staging:
        temporary = Path(staging) / "edited.nup"
        with open_container(path) as reader:
            index = int(request.get("package", 0))
            if not 0 <= index < len(reader.packages):
                raise ValueError("Select a valid package index.")
            records = [app_meta(reader, package) for package in reader.packages]
            records[index] = M.merge_app_meta(records[index], **changes)
            blocks = [M.serialize_block(record) for record in records]
            meta_starts = [p.meta_offset for p in reader.packages if p.meta_size]
            blob_end = min(meta_starts) if meta_starts else reader.super["file_size"]
            if any(offset + size > blob_end for _, _, _, offset, size, _ in reader.files):
                raise ValueError("Cannot edit this container: file extents overlap metadata.")
            header = reader.super
            if blob_end < header["blob_offset"]:
                raise ValueError("Metadata overlaps the table of contents.")
            toc = bytearray(reader._mm[header["toc_offset"]:header["toc_offset"] + header["toc_size"]])
            cursor = blob_end
            for i, (package, block) in enumerate(zip(reader.packages, blocks)):
                F._pkg_s.pack_into(toc, F._toc_head_s.size + i * F.PKG_SIZE,
                                  package.title_id, package.root_dir, package.exefs_dir,
                                  package.romfs_dir, package.version, package.kind,
                                  package.flags, 0, 0, cursor if block else 0, len(block))
                cursor += len(block)
            superblock = F.pack_super(F.MAGIC, header["header_size"], header["header_version"],
                                     header["toc_offset"], len(toc), hashlib.sha256(toc).digest(),
                                     header["blob_offset"], cursor, len(reader.packages), 0, header["uuid"])
            with path.open("rb") as original, temporary.open("xb") as target:
                copy_bytes(original, target, blob_end, check,
                           lambda done, total: report(done, total, "Copying unchanged content…"))
                for block in blocks:
                    target.write(block)
                target.seek(0)
                target.write(superblock)
                target.seek(header["toc_offset"])
                target.write(toc)
        validate_structure(temporary)
        check()
        if file_stamp(path) != original_stamp:
            raise ValueError("The original changed during editing; no replacement was made.")
        if inplace:
            os.replace(temporary, output)
        else:
            publish_file(temporary, output)
    return {"output": str(output), "package": index, "inplace": inplace}


def run_operation(request, check, report):
    if request["operation"] in ("preview_updates", "add_updates"):
        from .updates import add_updates, preview_updates
        operation = preview_updates if request["operation"] == "preview_updates" else add_updates
        return operation(request, check, report)
    if request["operation"] in ("shop_search", "shop_details", "shop_auto"):
        from .eshop import automatic_lookup, lookup_product, search_store
        operation = {"shop_search": search_store, "shop_details": lookup_product,
                     "shop_auto": automatic_lookup}[request["operation"]]
        return operation(request, check, report)
    operations = {"scan": scan_dump, "pack": pack_dump, "inspect": inspect_container,
                  "extract": extract_container, "edit": edit_container}
    if request["operation"] == "verify":
        return verify_container(require_path(request.get("file")), request.get("deep", True),
                                check, report, int(request.get("max_problems", 20)))
    return operations[request["operation"]](request, check, report)
