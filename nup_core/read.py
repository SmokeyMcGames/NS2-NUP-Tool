"""Validated NUP v1 index reader with independently owned file/mapping lifetime."""

import hashlib
import io
import mmap
import struct

import zstandard

from . import format as F, meta as M


class ExtentInput(io.RawIOBase):
    def __init__(self, handle, remaining):
        self.handle, self.remaining = handle, remaining

    def readable(self):
        return True

    def read(self, size=-1):
        count = self.remaining if size < 0 else min(size, self.remaining)
        block = self.handle.read(count)
        self.remaining -= len(block)
        return block

    def readinto(self, buffer):
        block = self.read(len(buffer))
        buffer[:len(block)] = block
        return len(block)


class NupReader:
    def __init__(self, path):
        self.path = str(path)
        self._fh = self._mm = None
        try:
            self._fh = open(path, "rb")
            length = self._fh.seek(0, 2)
            if length < F.HEADER_SIZE:
                raise F.NupError("Truncated NUP header")
            self._mm = mmap.mmap(self._fh.fileno(), 0, access=mmap.ACCESS_READ)
            self._read_index(length)
        except BaseException:
            self.close()
            raise

    def close(self):
        if self._mm is not None:
            self._mm.close()
            self._mm = None
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _read_index(self, length):
        fields = ("magic", "header_size", "header_version", "toc_offset", "toc_size",
                  "toc_sha256", "blob_offset", "file_size", "package_count", "flags", "uuid")
        header = self.super = dict(zip(fields, F._super_s.unpack_from(self._mm)))
        if (header["magic"] != F.MAGIC or header["header_size"] < F.HEADER_SIZE
                or header["header_version"] < 1 or header["flags"]
                or header["file_size"] != length or not header["package_count"]
                or any(self._mm[96:128])):
            raise F.NupError("Invalid or unsupported NUP header")
        start, size, blob = header["toc_offset"], header["toc_size"], header["blob_offset"]
        if (start != header["header_size"] or size < F._toc_head_s.size
                or start + size > blob or blob > length or blob % F.EXTENT_ALIGN):
            raise F.NupError("TOC/blob region is outside valid bounds")
        # Historical reference files have an unpadded TOC size. Accept that
        # layout; our writer emits the alignment specified for new containers.
        if hashlib.sha256(memoryview(self._mm)[start:start + size]).digest() != header["toc_sha256"]:
            raise F.NupError("TOC SHA-256 mismatch")
        magic, count, directories, files, pool_offset, pool_size, reserved = F._toc_head_s.unpack_from(self._mm, start)
        tables_end = F._toc_head_s.size + count * F.PKG_SIZE + directories * F.DIR_SIZE + files * F.FILE_SIZE
        if (magic != F.TOC_MAGIC or count != header["package_count"] or reserved or not directories
                or directories + files > 0xFFFFFFFF or tables_end > pool_offset
                or pool_offset + pool_size > size):
            raise F.NupError("Invalid TOC tables or string pool")
        self.dir_count, self.file_count = directories, files

        def name_at(offset, length):
            if offset + length > pool_size:
                raise F.NupError("Name is outside the string pool")
            name = bytes(self._mm[start + pool_offset + offset:start + pool_offset + offset + length])
            try:
                name.decode("utf-8")
            except UnicodeError as error:
                raise F.NupError("Invalid UTF-8 node name") from error
            return name

        cursor = start + F._toc_head_s.size
        self.packages = []
        regions = []
        for index in range(count):
            identity, root, exefs, romfs, version, kind, flags, r1, r2, offset, meta_size = F._pkg_s.unpack_from(self._mm, cursor)
            if (kind not in F.KIND_NAMES or flags & ~1 or r1 or r2 or any(self._mm[cursor + 44:cursor + 64])
                    or root >= directories or any(value != F.ABSENT and value >= directories for value in (exefs, romfs))):
                raise F.NupError("Invalid package record")
            if meta_size:
                if offset < blob or offset + meta_size > length or meta_size > 64 * 1024 * 1024:
                    raise F.NupError("Metadata is outside valid bounds")
                records = M.parse_block(self._mm[offset:offset + meta_size])
                for tag in (F.TLV_LOCALIZED_TITLES, F.TLV_LOCALIZED_ICONS):
                    if tag in records:
                        M.decode_localized(records[tag])
                regions.append((offset, offset + meta_size, ("metadata", index)))
            elif offset:
                raise F.NupError("Empty metadata must have a zero offset")
            self.packages.append(F.Package(identity, root, exefs, romfs, version, kind, flags, offset, meta_size, index))
            cursor += F.PKG_SIZE
        self.dirs = []
        for _ in range(directories):
            offset, length_name, first, child_count = F._dir_s.unpack_from(self._mm, cursor)
            if any(self._mm[cursor + 16:cursor + 24]):
                raise F.NupError("Unsupported directory flags")
            self.dirs.append((name_at(offset, length_name), first, child_count))
            cursor += F.DIR_SIZE
        self.files = []
        for _ in range(files):
            offset_name, length_name, unpacked, offset, stored, digest, codec, flags, reserved = F._file_s.unpack_from(self._mm, cursor)
            if codec not in (F.CODEC_RAW, F.CODEC_ZSTD) or flags or reserved or any(self._mm[cursor + 68:cursor + 80]):
                raise F.NupError("Unsupported file codec or flags")
            if unpacked == 0:
                if offset or stored or codec or digest != hashlib.sha256(b"").digest():
                    raise F.NupError("Invalid empty file record")
            else:
                if offset < blob or offset % F.EXTENT_ALIGN or not stored or offset + stored > length:
                    raise F.NupError("File extent is outside valid bounds")
                if codec == F.CODEC_RAW and unpacked != stored:
                    raise F.NupError("Raw extent size mismatch")
                regions.append((offset, offset + stored, ("file", digest, unpacked, codec)))
            self.files.append((name_at(offset_name, length_name), unpacked, digest, offset, stored, codec))
            cursor += F.FILE_SIZE
        slot_count = sum(count for _, _, count in self.dirs)
        if slot_count * 4 > pool_offset - tables_end:
            raise F.NupError("Child table is outside valid bounds")
        self.children = [entry[0] for entry in struct.iter_unpack("<I", self._mm[cursor:cursor + slot_count * 4])]
        if any(child >= directories + files for child in self.children):
            raise F.NupError("A child node points outside the node tables")
        self._validate_trees()
        previous = None
        for region in sorted(regions):
            if previous and region[0] < previous[1] and region != previous:
                raise F.NupError("Payload or metadata regions overlap")
            previous = region

    def _validate_trees(self):
        slots_used, reached = set(), set()
        roots = [package.root_dir for package in self.packages]
        if len(set(roots)) != len(roots) or sum(p.kind == F.KIND_BASE for p in self.packages) > 1:
            raise F.NupError("Duplicate roots or multiple base packages")
        has_base = any(p.kind == F.KIND_BASE for p in self.packages)
        for package in self.packages:
            if package.kind == F.KIND_UPDATE and bool(package.flags & 1) == has_base:
                raise F.NupError("Update standalone flag does not match the package layout")
            pending, package_dirs = [package.root_dir], set()
            while pending:
                node = pending.pop()
                if node in reached:
                    raise F.NupError("Cycle or repeated node reference")
                reached.add(node)
                if node >= self.dir_count:
                    continue
                package_dirs.add(node)
                _, first, count = self.dirs[node]
                if first + count > len(self.children):
                    raise F.NupError("Directory child range is outside the table")
                names = []
                for slot in range(first, first + count):
                    if slot in slots_used:
                        raise F.NupError("Overlapping directory child ranges")
                    slots_used.add(slot)
                    child = self.children[slot]
                    names.append((self.dirs[child] if child < self.dir_count else self.files[child - self.dir_count])[0])
                    pending.append(child)
                if names != sorted(set(names)):
                    raise F.NupError("Directory names must be unique and sorted")
            if any(value != F.ABSENT and value not in package_dirs for value in (package.exefs_dir, package.romfs_dir)):
                raise F.NupError("Content directory belongs to another package")
        if len(reached) != self.dir_count + self.file_count or len(slots_used) != len(self.children):
            raise F.NupError("Container includes unreachable nodes or child slots")

    def iter_file_chunks(self, index, chunk_size=4 * 1024 * 1024):
        _, size, expected, offset, stored, codec = self.files[index]
        digest, consumed = hashlib.sha256(), 0
        with open(self.path, "rb") as source:
            source.seek(offset)
            extent = ExtentInput(source, stored)
            stream = zstandard.ZstdDecompressor().stream_reader(extent) if codec else extent
            try:
                while block := stream.read(chunk_size):
                    consumed += len(block)
                    if consumed > size:
                        raise F.NupError("Payload exceeds its declared size")
                    digest.update(block)
                    yield block
            finally:
                stream.close()
        if consumed != size or digest.digest() != expected:
            raise F.NupError("Payload size or SHA-256 mismatch")

    def read_file(self, index):
        return b"".join(self.iter_file_chunks(index))
