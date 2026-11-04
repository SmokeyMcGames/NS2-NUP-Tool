"""NUP v1 table serialization and container assembly.

Payload compression is supplied as a callback, allowing the app to retain its
bounded-memory compressor and cancellation/progress handling without monkeypatches.
"""

import hashlib
from pathlib import Path
import struct

import zstandard

from . import format as F, meta as M
from .discover import ARTIFACT_NAMES, DirObj, Tree, discover


def _derive_uuid(packages):
    identity = b"".join(struct.pack("<QIB", p.title_id, p.version, p.kind) for p in packages)
    return hashlib.sha256(identity).digest()[:16]


def _locate_content_dirs(packages, roots):
    records = []
    for index, (package, root) in enumerate(zip(packages, roots)):
        folders = {node.name: node.id for node in root.children if isinstance(node, DirObj)}
        records.append(F.Package(package.title_id, root.id, folders.get(b"exefs", F.ABSENT),
                                 folders.get(b"romfs", F.ABSENT), package.version,
                                 package.kind, package.flags, index=index))
    return records


def _build_toc(tree, records, metadata, dir_count, file_count, toc_size):
    for node in [*tree.dirs, *tree.files]:
        tree.intern(node.name)
    pool_offset = (F._toc_head_s.size + len(records) * F.PKG_SIZE + dir_count * F.DIR_SIZE
                   + file_count * F.FILE_SIZE + len(tree.children) * 4)
    if toc_size < pool_offset + tree.pool_size:
        raise F.NupError("TOC reservation is too small")
    result = bytearray(F._toc_head_s.pack(F.TOC_MAGIC, len(records), dir_count, file_count,
                                         pool_offset, tree.pool_size, 0))
    for package, (offset, size) in zip(records, metadata):
        result.extend(F._pkg_s.pack(package.title_id, package.root_dir, package.exefs_dir,
                                   package.romfs_dir, package.version, package.kind,
                                   package.flags, 0, 0, offset, size))
    for node in tree.dirs:
        result.extend(F._dir_s.pack(tree.intern(node.name), len(node.name), node.first_child, node.child_count))
    for node in tree.files:
        result.extend(F._file_s.pack(tree.intern(node.name), len(node.name), node.size,
                                    node.extent_offset, node.extent_size, node.sha256,
                                    node.codec, node.codec_flags, 0))
    for child in tree.children:
        result.extend(struct.pack("<I", child))
    result.extend(tree.pool)
    result.extend(bytes(toc_size - len(result)))
    return bytes(result)


def pack(output, source, *, level=3, keep_listings=False, base_title_id=None, names=None,
         icons=None, publisher=None, display_version=None, packages=None, tree_type=Tree,
         metadata_builder=None, extent_writer=None):
    if extent_writer is None:
        raise ValueError("A streaming extent writer is required")
    selected = packages if packages is not None else discover(source, base_title_id)
    tree = tree_type(set() if keep_listings else ARTIFACT_NAMES)
    roots = [tree.add_tree(package.src) for package in selected]
    tree.assign(roots)
    for node in [*tree.dirs, *tree.files]:
        tree.intern(node.name)
    records = _locate_content_dirs(selected, roots)
    size = F.aligned(F._toc_head_s.size + len(records) * F.PKG_SIZE + len(tree.dirs) * F.DIR_SIZE
                     + len(tree.files) * F.FILE_SIZE + len(tree.children) * 4 + tree.pool_size)
    blob = F.aligned(F.HEADER_SIZE + size)
    app_index = next((i for i, p in enumerate(selected) if p.kind == F.KIND_BASE), 0)
    make_metadata = metadata_builder or M.meta_block
    blocks = [make_metadata(package, names or {}, icons or {}, publisher, display_version, i == app_index, Path(source).name)
              for i, package in enumerate(selected)]
    with Path(output).open("xb") as target:
        target.seek(blob)
        extent_writer(target, tree, zstandard.ZstdCompressor(level=level), blob, None)
        metadata = []
        for block in blocks:
            metadata.append((target.tell() if block else 0, len(block)))
            target.write(block)
        end = target.tell()
        toc = _build_toc(tree, records, metadata, len(tree.dirs), len(tree.files), size)
        header = F.pack_super(F.MAGIC, F.HEADER_SIZE, 1, F.HEADER_SIZE, size,
                              hashlib.sha256(toc).digest(), blob, end, len(records), 0, _derive_uuid(records))
        target.seek(0)
        target.write(header)
        target.write(toc)
        target.truncate(end)
    return output
