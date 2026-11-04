"""Replace older updates while copying retained compressed extents unchanged."""

from contextlib import ExitStack
import copy
import hashlib
import shutil
import tempfile
from pathlib import Path

from nup_core import format as F, meta as M
from nup_core.discover import DirObj, FileObj, PackInput, Tree
from nup_core.pack import _build_toc, _derive_uuid, _locate_content_dirs

from .backend import (file_stamp, new_output, publish_file, require_path, scan_dump,
                      validate_structure, verify_container)
from .streaming import copy_bytes, open_container, pack_streamed
from .discovery import VERSION_FALLBACK_WARNING, discover_packages, update_version
from .launch import (child_directory, has_launch_policy, overlay_directory,
                     replace_base_content, replaces_base_content)


def update_plan(request, check, report):
    """Re-evaluate both sources; a preview never authorizes stale input."""
    original = require_path(request.get("file"))
    validate_structure(original)
    with open_container(original) as reader:
        base_ids = {p.title_id for p in reader.packages if p.kind == F.KIND_BASE}
        if len(base_ids) != 1 or 0 in base_ids:
            raise ValueError("Adding updates requires a NUP with one known base-game title ID.")
        target_id = next(iter(base_ids))
        versions = [p.version for p in reader.packages
                    if p.kind == F.KIND_UPDATE and p.title_id == target_id]
        highest = max(versions, default=0)
        existing_count = len(reader.packages)
        prefer_program = any(has_launch_policy(M.parse_block(bytes(reader._mm[p.meta_offset:p.meta_offset + p.meta_size])))
                             for p in reader.packages if p.kind == F.KIND_BASE)
        replace_content = any(replaces_base_content(M.parse_block(bytes(reader._mm[p.meta_offset:p.meta_offset + p.meta_size])))
                              for p in reader.packages if p.kind == F.KIND_BASE)
    source_value = request.get("update_source", "")
    if not source_value:
        raise ValueError("Choose a decrypted update folder or an update-only NUP.")
    source = Path(source_value).expanduser().resolve()
    if source == original:
        raise ValueError("Choose an update source different from the existing NUP.")
    unknown = False
    warnings = []
    if source.is_file():
        validate_structure(source)
        with open_container(source) as reader:
            packages = list(reader.packages)
            size = source.stat().st_size
            largest = 0
    else:
        source = require_path(source, directory=True)
        scan = scan_dump({"source": str(source), "keep_listings": request.get("keep_listings", False),
                          "update_version": request.get("update_version", "")}, check, report)
        if scan["unassigned_content"]:
            raise ValueError("Unrecognized update/DLC content must be corrected before adding updates: "
                             + ", ".join(scan["unassigned_content"]))
        packages = discover_packages(source, version=request.get("update_version", ""),
                                     keep_listings=request.get("keep_listings", False))
        if len(packages) == 1 and packages[0].kind == F.KIND_BASE and Path(packages[0].src) == source:
            version = update_version(source, request.get("update_version", ""), packages[0].npdm)
            packages[0].kind = F.KIND_UPDATE
            packages[0].version = version or 0
        size, largest = scan["size"], scan["largest"]
        warnings = scan["warnings"]
    if not packages:
        raise ValueError("No updates were found.")
    for package in packages:
        check()
        if package.kind != F.KIND_UPDATE:
            raise ValueError("The update source must contain only update packages; choose an update folder or update-only NUP.")
        if package.title_id not in (0, target_id):
            raise ValueError(f"Different game: update {package.title_id:016X}, existing NUP {target_id:016X}.")
    newest = max(p.version for p in packages)
    version_defaulted = newest == 0
    if not version_defaulted and newest <= highest:
        raise ValueError(f"Update {newest} is already present or older than the newest included update ({highest}).")
    if version_defaulted:
        if VERSION_FALLBACK_WARNING not in warnings:
            warnings.append(VERSION_FALLBACK_WARNING)
        warnings.append("Update order cannot be verified for V0. Saving will replace the existing update with this selected content.")
    ignored = sorted({p.version for p in packages if p.version != newest})
    packages = [p for p in packages if p.version == newest]
    if len(packages) != 1:
        raise ValueError(f"The source contains duplicate update version {newest}.")
    rows = []
    for package in packages:
        unknown = package.title_id == 0
        rows.append({"version": package.version, "title_id": f"{package.title_id:016X}",
                     "identity": "unconfirmed" if package.title_id == 0 else "match"})
        if isinstance(package, PackInput):
            package.title_id = target_id
            # The staging NUP has no base yet; clear this flag only after merging.
            package.flags |= F.PKG_FLAG_STANDALONE_UPDATE
    return {"title_id": f"{target_id:016X}", "current_version": highest,
            "existing_packages": existing_count, "updates": rows,
            "kept_packages": existing_count - len(versions),
            "replaced_versions": sorted(versions), "ignored_versions": ignored,
            "requires_confirmation": unknown, "warnings": warnings,
            "version_defaulted": version_defaulted,
            "prefer_update_executable": prefer_program,
            "replace_base_content": replace_content,
            "source_size": size, "largest": largest, "source": str(source),
            "source_kind": "nup" if source.is_file() else "dump"}, packages


def preview_updates(request, check, report):
    plan, _ = update_plan(request, check, report)
    return plan


def clone_tree(reader, root_id, sources, check):
    """Copy TOC nodes, retaining a reference to each stored source extent."""
    root = DirObj(reader.dirs[root_id][0])
    pending = [(root_id, root)]
    visited = set()
    while pending:
        check()
        directory, node = pending.pop()
        if directory in visited:
            raise ValueError("A package directory is referenced more than once.")
        visited.add(directory)
        _, first, count = reader.dirs[directory]
        for child in reader.children[first:first + count]:
            if child < reader.dir_count:
                nested = DirObj(reader.dirs[child][0])
                pending.append((child, nested))
                node.children.append(nested)
            else:
                index = child - reader.dir_count
                name, size, sha, offset, stored, codec = reader.files[index]
                file = FileObj(name, str(reader.path))
                file.size, file.sha256, file.extent_size, file.codec = size, sha, stored, codec
                sources[file] = (reader.path, offset)
                node.children.append(file)
    return root


def merge_containers(original, incoming, output, target_id, newest, check, report):
    """Serialize new tables while retaining the existing compressed extents."""
    with ExitStack() as stack:
        readers = [stack.enter_context(open_container(p)) for p in (original, incoming)]
        tree, roots, identities, metadata, sources = Tree(set()), [], [], [], {}
        for reader_index, reader in enumerate(readers):
            for package in reader.packages:
                check()
                if reader_index == 0 and package.kind == F.KIND_UPDATE and package.title_id == target_id:
                    continue
                if reader_index == 1 and package.version != newest:
                    continue
                roots.append(clone_tree(reader, package.root_dir, sources, check))
                identity = PackInput(package.kind, "", package.title_id, package.version, package.flags)
                if reader_index == 1:
                    identity.title_id = target_id
                    identity.flags &= ~F.PKG_FLAG_STANDALONE_UPDATE
                identities.append(identity)
                block = bytes(reader._mm[package.meta_offset:package.meta_offset + package.meta_size])
                if reader_index == 1 or (package.kind == F.KIND_BASE and package.title_id == target_id):
                    block = M.serialize_block(M.merge_app_meta(M.parse_block(block), display_version=f"V{newest}"))
                metadata.append(block)
        refresh_preferred_program(roots, identities, metadata, sources)
        tree.assign(roots)
        for node in [*tree.dirs, *tree.files]:
            tree.intern(node.name)
        records = _locate_content_dirs(identities, roots)
        toc_size = F.aligned(F._toc_head_s.size + len(records) * F.PKG_SIZE + len(tree.dirs) * F.DIR_SIZE
                             + len(tree.files) * F.FILE_SIZE + len(tree.children) * 4 + tree.pool_size)
        blob_offset = (F.HEADER_SIZE + toc_size + F.EXTENT_ALIGN - 1) & ~(F.EXTENT_ALIGN - 1)
        handles = {reader.path: stack.enter_context(open(reader.path, "rb")) for reader in readers}
        with output.open("xb") as target:
            target.seek(blob_offset)
            seen = {}
            for index, file in enumerate(tree.files):
                check()
                key = (file.sha256, file.size)
                if file.size == 0:
                    file.extent_offset = file.extent_size = 0
                    file.codec = F.CODEC_RAW
                elif key in seen:
                    file.extent_offset, file.extent_size, file.codec = seen[key]
                else:
                    offset = (target.tell() + F.EXTENT_ALIGN - 1) & ~(F.EXTENT_ALIGN - 1)
                    target.write(b"\0" * (offset - target.tell()))
                    source, source_offset = sources[file]
                    handles[source].seek(source_offset)
                    copy_bytes(handles[source], target, file.extent_size, check,
                               lambda done, total: report(index, len(tree.files),
                                   f"Copying stored content · {done:,} / {total:,} bytes"))
                    file.extent_offset = offset
                    seen[key] = (offset, file.extent_size, file.codec)
                report(index + 1, len(tree.files), "Copying base, DLC and the newest update…")
            offsets = []
            for block in metadata:
                offsets.append((target.tell() if block else 0, len(block)))
                target.write(block)
            file_size = target.tell()
            toc = _build_toc(tree, records, offsets, len(tree.dirs), len(tree.files), toc_size)
            header = F.pack_super(F.MAGIC, F.HEADER_SIZE, 1, F.HEADER_SIZE, toc_size,
                                  hashlib.sha256(toc).digest(), blob_offset, file_size,
                                  len(records), 0, _derive_uuid(records))
            target.seek(0)
            target.write(header)
            target.write(toc)
            target.truncate(file_size)


def refresh_preferred_program(roots, identities, metadata, sources):
    """Maintain the base-content policy recorded when this NUP was created."""
    base_index = next(i for i, package in enumerate(identities) if package.kind == F.KIND_BASE)
    base_meta = M.parse_block(metadata[base_index])
    if not has_launch_policy(base_meta):
        return
    update_index = next(i for i, package in enumerate(identities) if package.kind == F.KIND_UPDATE)
    update_exefs = child_directory(roots[update_index], b"exefs")
    if update_exefs is None or not any(isinstance(n, FileObj) and n.name == b"main" and n.size > 0
                                       for n in update_exefs.children):
        return

    def clone(node):
        if isinstance(node, FileObj):
            result = copy.copy(node)
            sources[result] = sources[node]
        else:
            result = DirObj(node.name)
            result.children = [clone(child) for child in node.children]
        return result

    if replaces_base_content(base_meta):
        replace_base_content(roots[base_index], roots[update_index], clone)
        base_meta.pop(F.TLV_NPDM, None)
    else:
        # Existing 0.2.3 NUPs retain their original ExeFS-only overlay policy.
        base_exefs = child_directory(roots[base_index], b"exefs")
        if base_exefs is None:
            base_exefs = DirObj(b"exefs")
            roots[base_index].children.append(base_exefs)
            roots[base_index].children.sort(key=lambda child: child.name)
        overlay_directory(base_exefs, update_exefs, clone)
    update_meta = M.parse_block(metadata[update_index])
    base_meta.pop(F.TLV_BUILD_ID, None)
    for tag in (F.TLV_NPDM, F.TLV_BUILD_ID):
        if tag in update_meta:
            base_meta[tag] = update_meta[tag]
    metadata[base_index] = M.serialize_block(base_meta)


def add_updates(request, check, report):
    original = require_path(request.get("file"))
    original_stamp = file_stamp(original)
    plan, packages = update_plan(request, check, report)
    if plan["requires_confirmation"] and not request.get("confirm_identity", False):
        raise ValueError("The update has no title ID. Confirm that it belongs to this game before adding it.")
    source = Path(plan["source"])
    source_stamp = file_stamp(source) if source.is_file() else None
    output = new_output(request.get("output"), source if source.is_dir() else None)
    if output.suffix.lower() != ".nup":
        raise ValueError("Use the .nup extension for the updated copy.")
    level = int(request.get("level", 3))
    if not -5 <= level <= 22:
        raise ValueError("Compression level must be between -5 and 22.")
    required = original.stat().st_size + plan["source_size"] * 2 + plan["largest"] + 32 * 1024 * 1024
    if shutil.disk_usage(output.parent).free < required:
        raise ValueError("Insufficient space for the updated copy and temporary update data.")
    with tempfile.TemporaryDirectory(prefix=".nup-update-", dir=output.parent) as staging:
        staging = Path(staging)
        incoming = source
        if plan["source_kind"] == "dump":
            incoming = staging / "incoming.nup"
            report(0, 0, "Compressing the new update only…")
            pack_streamed(incoming, source, check=check, report=report, packages=packages,
                          level=level, keep_listings=request.get("keep_listings", False))
        temporary = staging / "updated.nup"
        merge_containers(original, incoming, temporary, int(plan["title_id"], 16),
                         plan["updates"][0]["version"], check, report)
        report(0, 0, "Verifying every file in the updated container…")
        verification = verify_container(temporary, True, check, report)
        if not verification["ok"]:
            raise ValueError("Updated container failed verification: " + "\n".join(verification["problems"]))
        check()
        if file_stamp(original) != original_stamp or (source_stamp and file_stamp(source) != source_stamp):
            raise ValueError("An input NUP changed during the operation; no output was published.")
        publish_file(temporary, output)
    return {"output": str(output), "size": output.stat().st_size,
            "added_versions": [row["version"] for row in plan["updates"]],
            "removed_versions": plan["replaced_versions"],
            "packages": plan["kept_packages"] + len(packages), "verification": verification}
