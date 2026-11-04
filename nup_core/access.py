"""Metadata and tree accessors used by the desktop workflows."""

from dataclasses import dataclass
from pathlib import Path

from . import format as F, meta as M


@dataclass(frozen=True)
class NodeRef:
    name: bytes
    index: int
    is_dir: bool


def iter_children(reader, directory):
    _, first, count = reader.dirs[directory]
    for child in reader.children[first:first + count]:
        is_dir = child < reader.dir_count
        index = child if is_dir else child - reader.dir_count
        yield NodeRef((reader.dirs if is_dir else reader.files)[index][0], index, is_dir)


def resolve_path(reader, package, path):
    current = NodeRef(reader.dirs[package.root_dir][0], package.root_dir, True)
    parts = [part for part in path.replace("\\", "/").split("/") if part]
    for position, part in enumerate(parts):
        if not current.is_dir or part in (".", ".."):
            return None
        pointer = {"exefs": package.exefs_dir, "romfs": package.romfs_dir}.get(part, F.ABSENT)
        if position == 0 and pointer != F.ABSENT:
            current = NodeRef(reader.dirs[pointer][0], pointer, True)
        else:
            current = next((node for node in iter_children(reader, current.index) if node.name == part.encode("utf-8")), None)
            if current is None:
                return None
    return current


def app_meta(reader, package):
    return M.parse_block(reader._mm[package.meta_offset:package.meta_offset + package.meta_size])


def localized_titles(reader, package):
    return M.decode_localized(app_meta(reader, package).get(F.TLV_LOCALIZED_TITLES, b""))


def localized_icons(reader, package):
    return M.decode_localized(app_meta(reader, package).get(F.TLV_LOCALIZED_ICONS, b""))


def build_id(reader, package):
    return app_meta(reader, package).get(F.TLV_BUILD_ID)


def extract_tree(reader, output, directory):
    # Reuse the app's transactional workflow's Windows-safe filename validation.
    from ns2_nup_tool.backend import extract_directory
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    return extract_directory(reader, directory, root, lambda: None, lambda *args: None)
