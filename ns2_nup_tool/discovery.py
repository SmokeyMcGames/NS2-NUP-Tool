"""App bundle and flat-update layouts layered over the project format backend."""

import os
import struct
import uuid
from contextlib import contextmanager
from pathlib import Path

from nup_core import format as F
from nup_core.discover import _collect_dlcs, discover
from .bundle import SIDECAR, read_bundle_packages

VERSION_FALLBACK_WARNING = (
    "Warning: the update's version is unavailable or set to 0. Using V0 as a placeholder; "
    "this does not identify its actual release. You can enter the correct numeric version if known."
)


def update_version(folder, override="", npdm=None):
    """Prefer an explicit/package-folder version; zero NPDM versions are unknown."""
    value = str(override if override is not None else "").strip()
    if value:
        if not value.isascii() or not value.isdecimal() or not 0 <= int(value) <= 0xFFFFFFFF:
            raise ValueError("Enter the update's decimal numeric version, between 0 and 4294967295 (not 1.2.3).")
        return int(value)
    name = Path(folder).name
    if name.isascii() and name.isdecimal() and 0 < int(name) <= 0xFFFFFFFF:
        return int(name)
    if npdm and len(npdm) >= 0x80 and npdm[:4] == b"META":
        version = struct.unpack_from("<I", npdm, 0x18)[0]
        if version:
            return version
    return None


def discover_packages(source, title_id=None, version="", *, keep_listings=False):
    source = Path(source)
    restored = read_bundle_packages(source, title_id)
    if restored is None:
        packages = discover_layout(source, title_id, version)
    else:
        # Keep saved identities while discovering newly added updates and DLC.
        known = {Path(p.src).resolve() for p in restored}
        try:
            added = discover_layout(source, title_id, version)
        except SystemExit:
            added = []
        packages = restored + [p for p in added if Path(p.src).resolve() not in known]
    roots = {Path(p.src).resolve() for p in packages}
    owner = next((p for p in packages if p.kind == F.KIND_BASE), packages[0])
    owner.loose_content, owner.unassigned_content = [], []
    if source.resolve() not in roots:
        for parent, dirs, files in os.walk(source):
            parent = Path(parent)
            for name in list(dirs):
                path = parent / name
                if path.resolve() in roots or (parent == source and name == SIDECAR and restored is not None):
                    dirs.remove(name)
                elif not any(path.resolve() in root.parents for root in roots):
                    files.append(name)
                    dirs.remove(name)
            for name in files:
                path = parent / name
                if name == ".listing" and not keep_listings and path.is_file():
                    continue
                relative = path.relative_to(source)
                if relative.parts[0] in ("updates", "dlc"):
                    owner.unassigned_content.append(str(relative))
                else:
                    owner.loose_content.append(str(path))
    return packages


def discover_layout(source, title_id=None, version=""):
    """Also recognize a single update directly inside updates/exefs or updates/romfs."""
    source = Path(source)
    updates = source / "updates"
    direct = any((updates / name).is_dir() for name in ("exefs", "romfs"))
    if not direct:
        return discover(str(source), title_id)
    if updates.is_symlink() or updates.is_junction():
        raise ValueError(f"Linked update folders are not supported: {updates}")
    nested = [path for path in updates.iterdir() if path.name.isdecimal() and path.is_dir()
              and any((path / name).is_dir() for name in ("exefs", "romfs"))]
    if nested:
        raise ValueError("The updates folder mixes direct content with numbered update folders. Choose one layout to avoid packing overlapping content.")
    has_base = (source / "base").is_dir()
    packages = discover(str(source), title_id) if has_base else (
        _collect_dlcs(str(source / "dlc")) if (source / "dlc").is_dir() else [])
    package = discover(str(updates), None)[0]
    package.kind = F.KIND_UPDATE
    detected = update_version(updates, version, package.npdm)
    package.version = detected or 0
    package.flat_update = True
    package.flags = 0 if has_base else F.PKG_FLAG_STANDALONE_UPDATE
    base_id = next((p.title_id for p in packages if p.kind == F.KIND_BASE), title_id or 0)
    if package.title_id and base_id and package.title_id != base_id:
        raise ValueError("The direct update's title ID does not match the base game.")
    package.title_id = package.title_id or base_id
    packages.insert(1 if has_base else 0, package)
    return packages


@contextmanager
def correct_update_layout(source, flat_update):
    """Move the complete flat update into its numbered folder; undo on failure."""
    if flat_update is None:
        yield
        return
    source = Path(source).resolve()
    updates = source / "updates"
    target = updates / str(flat_update["version"])
    if updates.is_symlink() or updates.is_junction() or target.exists():
        raise ValueError(f"Cannot correct the update layout safely: {target}")
    if not any((updates / name).is_dir() for name in ("exefs", "romfs")):
        raise ValueError("The update layout changed after scanning. Scan the dump again.")
    holding = source / f".nup-layout-{uuid.uuid4().hex}"
    # Rename the whole directory so companion files are preserved too. No payload
    # copies are needed, even for large updates on the same volume.
    updates.rename(holding)
    wrapper_created = content_moved = False
    try:
        updates.mkdir()
        wrapper_created = True
        holding.rename(target)
        content_moved = True
        yield
    except BaseException as error:
        try:
            if content_moved:
                target.rename(holding)
            if wrapper_created:
                updates.rmdir()  # Only remove the empty wrapper we created.
            holding.rename(updates)
        except OSError as restore_error:
            raise RuntimeError(
                f"Packing failed and the original layout could not be restored: {restore_error}. "
                f"Update data is preserved at {holding if holding.exists() else target}."
            ) from error
        raise
