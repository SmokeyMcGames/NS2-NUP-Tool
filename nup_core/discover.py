"""Filesystem discovery and a deterministic, in-memory directory model."""

from dataclasses import dataclass, field
from pathlib import Path
import re
import struct

from . import format as F

ARTIFACT_NAMES = {b".listing"}


@dataclass(eq=False)
class FileObj:
    name: bytes
    src_path: str
    size: int = 0
    sha256: bytes = bytes(32)
    extent_offset: int = 0
    extent_size: int = 0
    codec: int = 0
    codec_flags: int = 0
    id: int = 0


@dataclass(eq=False)
class DirObj:
    name: bytes
    children: list = field(default_factory=list)
    id: int = 0
    first_child: int = 0
    child_count: int = 0


@dataclass
class PackInput:
    kind: int
    src: str
    title_id: int = 0
    version: int = 0
    flags: int = 0
    npdm: bytes | None = None
    build_id: bytes | None = None


def parse_npdm_program_id(data):
    offset = data.find(b"ACI0")
    return struct.unpack_from("<Q", data, offset + 16)[0] if 0 <= offset <= len(data) - 24 else None


def _resolve_title_id(package, override=None):
    root = Path(package.src)
    for candidate in (root / "exefs/main.npdm", root / "main.npdm"):
        if candidate.is_file():
            if candidate.stat().st_size > 64 * 1024 * 1024:
                raise F.NupError("NPDM metadata exceeds the supported size")
            package.npdm = candidate.read_bytes()
            package.title_id = parse_npdm_program_id(package.npdm) or package.title_id
            break
    if override is not None:
        package.title_id = override
    for candidate in (root / "exefs/main", root / "main"):
        if candidate.is_file():
            with candidate.open("rb") as executable:
                header = executable.read(96)
            if len(header) >= 96 and (header[:4] == b"NSO0" or header[16:20] == b"NRO0"):
                package.build_id = header[64:96]
            break


def _has_content(path):
    return any((path / name).is_dir() for name in ("exefs", "romfs"))


def _collect_dlcs(source):
    packages = []
    for title in sorted(Path(source).iterdir()):
        if not title.is_dir() or not re.fullmatch(r"[0-9a-fA-F]{16}", title.name):
            continue
        for content in sorted(title.iterdir()):
            if content.is_dir() and _has_content(content):
                package = PackInput(F.KIND_ADDON, str(content), int(title.name, 16))
                _resolve_title_id(package, package.title_id)
                packages.append(package)
    return packages


def discover(source, title_id=None):
    root = Path(source)
    packages = []
    base_root = root / "base"
    if base_root.is_dir() and _has_content(base_root):
        base = PackInput(F.KIND_BASE, str(base_root))
        _resolve_title_id(base, title_id)
        packages.append(base)
    updates = root / "updates"
    if updates.is_dir():
        for folder in sorted(updates.iterdir(), key=lambda p: (int(p.name) if p.name.isascii() and p.name.isdecimal() else -1, p.name)):
            if folder.is_dir() and folder.name.isascii() and folder.name.isdecimal() and _has_content(folder):
                package = PackInput(F.KIND_UPDATE, str(folder), version=int(folder.name),
                                    flags=0 if packages and packages[0].kind == F.KIND_BASE else 1)
                _resolve_title_id(package)
                if not package.title_id:
                    package.title_id = packages[0].title_id if packages and packages[0].kind == F.KIND_BASE else (title_id or 0)
                packages.append(package)
    if (root / "dlc").is_dir():
        packages.extend(_collect_dlcs(root / "dlc"))
    if not packages and _has_content(root):
        package = PackInput(F.KIND_BASE, str(root))
        _resolve_title_id(package, title_id)
        packages.append(package)
    if not packages:
        raise SystemExit("No ExeFS/RomFS packages were found in this folder.")
    return packages


class Tree:
    def __init__(self, artifacts=None):
        self.artifacts = ARTIFACT_NAMES if artifacts is None else artifacts
        self.dirs, self.files, self.children = [], [], []
        self.pool = bytearray()
        self.strings = {}

    @property
    def pool_size(self):
        return len(self.pool)

    def intern(self, name):
        if name not in self.strings:
            self.strings[name] = len(self.pool)
            self.pool.extend(name)
        return self.strings[name]

    def add_tree(self, source):
        root = DirObj(b"")
        pending = [(Path(source), root)]
        while pending:
            path, directory = pending.pop()
            if path.is_symlink() or path.is_junction():
                raise F.NupError(f"Linked source directory is unsupported: {path}")
            for entry in sorted(path.iterdir(), key=lambda p: p.name.encode("utf-8")):
                name = entry.name.encode("utf-8")
                if name in self.artifacts:
                    continue
                if entry.is_symlink() or entry.is_junction():
                    raise F.NupError(f"Linked source entry is unsupported: {entry}")
                if entry.is_dir():
                    child = DirObj(name)
                    pending.append((entry, child))
                elif entry.is_file():
                    child = FileObj(name, str(entry))
                else:
                    raise F.NupError(f"Unsupported source entry: {entry}")
                directory.children.append(child)
        return root

    def assign(self, roots):
        self.dirs, self.files, self.children = [], [], []
        pending, visited = list(reversed(roots)), set()
        while pending:
            node = pending.pop()
            if id(node) in visited:
                raise F.NupError("A source node belongs to more than one parent")
            visited.add(id(node))
            if isinstance(node, DirObj):
                node.id = len(self.dirs)
                self.dirs.append(node)
                node.children.sort(key=lambda item: item.name)
                if len({n.name for n in node.children}) != len(node.children):
                    raise F.NupError("Duplicate child names")
                pending.extend(reversed(node.children))
            else:
                node.id = len(self.files)
                self.files.append(node)
        for directory in self.dirs:
            directory.first_child = len(self.children)
            directory.child_count = len(directory.children)
            self.children.extend(node.id if isinstance(node, DirObj) else len(self.dirs) + node.id
                                 for node in directory.children)
