"""Bounded-memory payload I/O for the project's own NUP format implementation."""

from __future__ import annotations

import hashlib
import io
import os
import tempfile
from contextlib import contextmanager

import zstandard
from nup_core import format as F
from nup_core import pack as pack_module
from nup_core.read import NupReader
from nup_core.discover import DirObj, FileObj

from .launch import clone_source_node, mark_launch_policy, replace_base_content
from .bundle import merge_saved_metadata

CHUNK_SIZE = 4 * 1024 * 1024


@contextmanager
def open_container(path):
    with NupReader(str(path)) as reader:
        yield reader


def copy_bytes(source, target, count, check, report=None):
    copied = 0
    while copied < count:
        check()
        block = source.read(min(CHUNK_SIZE, count - copied))
        if not block:
            raise ValueError("The source changed or ended unexpectedly during copying.")
        target.write(block)
        copied += len(block)
        if report:
            report(copied, count)


def pack_streamed(output, source, *, check, report, packages=None, **options):
    def write_extents(out, tree, compressor, cursor, progress):
        seen = {}
        for index, node in enumerate(tree.files):
            check()
            with open(node.src_path, "rb") as original, tempfile.TemporaryFile(
                dir=os.path.dirname(output)
            ) as compressed:
                before = os.fstat(original.fileno())
                digest = hashlib.sha256()
                consumed = 0
                with compressor.stream_writer(
                    compressed, size=before.st_size, closefd=False
                ) as writer:
                    while block := original.read(CHUNK_SIZE):
                        check()
                        digest.update(block)
                        writer.write(block)
                        consumed += len(block)
                        report(index, len(tree.files),
                               f"Compressing {os.path.basename(node.src_path)} · "
                               f"{consumed:,} / {before.st_size:,} bytes")
                after = os.fstat(original.fileno())
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError(f"Source changed while packing: {node.src_path}")
                node.size = consumed
                node.sha256 = digest.digest()
                if not node.size:
                    node.extent_offset = node.extent_size = 0
                    node.codec = F.CODEC_RAW
                elif node.sha256 in seen:
                    node.extent_offset, node.extent_size, node.codec = seen[node.sha256]
                else:
                    packed_size = compressed.tell()
                    use_compressed = packed_size < node.size
                    payload = compressed if use_compressed else original
                    payload.seek(0)
                    node.extent_size = packed_size if use_compressed else node.size
                    node.codec = F.CODEC_ZSTD if use_compressed else F.CODEC_RAW
                    aligned = (cursor + F.EXTENT_ALIGN - 1) & ~(F.EXTENT_ALIGN - 1)
                    out.write(b"\0" * (aligned - cursor))
                    node.extent_offset = aligned
                    copy_bytes(payload, out, node.extent_size, check)
                    cursor = aligned + node.extent_size
                    seen[node.sha256] = (aligned, node.extent_size, node.codec)
            report(index + 1, len(tree.files), f"Packed {os.path.basename(node.src_path)}")
        return cursor

    replacements = {p.src: p.launch_content for p in (packages or []) if hasattr(p, "launch_content")}
    loose_content = {p.src: p.loose_content for p in (packages or []) if getattr(p, "loose_content", [])}

    class LaunchTree(pack_module.Tree):
        def add_tree(self, src):
            if src not in replacements:
                root = super().add_tree(src)
                for path in loose_content.get(src, []):
                    name = os.path.basename(path).encode("utf-8")
                    if any(n.name.lower() == name.lower() for n in root.children):
                        raise ValueError(f"Loose dump content conflicts with package content: {path}")
                    if os.path.isdir(path):
                        node = super().add_tree(path)
                        node.name = name
                    else:
                        if name in self.artifacts:
                            continue
                        node = FileObj(name, path)
                    root.children.append(node)
                root.children.sort(key=lambda n: n.name)
            else:
                root = DirObj(b"")
                incoming = super().add_tree(replacements[src])
                replace_base_content(root, incoming, clone_source_node)
            return root

    def metadata_block(package, *args):
        block = merge_saved_metadata(package, pack_module.M.meta_block(package, *args))
        return mark_launch_policy(block) if hasattr(package, "launch_content") else block

    return pack_module.pack(str(output), str(source), packages=packages, tree_type=LaunchTree,
                            metadata_builder=metadata_block, extent_writer=write_extents, **options)


class ExtentReader(io.RawIOBase):
    """Limit decompression input to one extent without slicing an entire mmap."""

    def __init__(self, file, offset, size):
        super().__init__()
        self.file = file
        self.file.seek(offset)
        self.remaining = size

    def readable(self):
        return True

    def read(self, size=-1):
        size = self.remaining if size < 0 else min(size, self.remaining)
        data = self.file.read(size)
        self.remaining -= len(data)
        return data

    def readinto(self, buffer):
        data = self.read(len(buffer))
        buffer[:len(data)] = data
        return len(data)


def read_payload(reader, file_index, check, target=None, report=None):
    name, expected_size, expected_sha, offset, stored_size, codec = reader.files[file_index]
    if codec == F.CODEC_RAW and stored_size != expected_size:
        raise ValueError(f"Raw extent size mismatch: {name!r}")
    digest = hashlib.sha256()
    total = 0
    with open(reader.path, "rb") as file:
        extent = ExtentReader(file, offset, stored_size)
        stream = (zstandard.ZstdDecompressor().stream_reader(extent)
                  if codec == F.CODEC_ZSTD else extent)
        try:
            while block := stream.read(CHUNK_SIZE):
                check()
                total += len(block)
                if total > expected_size:
                    raise ValueError(f"Decompressed data exceeds declared size: {name!r}")
                digest.update(block)
                if target:
                    target.write(block)
                if report:
                    report(total, expected_size)
        finally:
            stream.close()
    if total != expected_size or digest.digest() != expected_sha:
        raise ValueError(f"Content size or SHA-256 mismatch: {name.decode('utf-8', 'replace')}")
