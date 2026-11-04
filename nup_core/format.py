"""Binary field layouts and value types for NUP v1 (little endian)."""

from dataclasses import dataclass
import struct

MAGIC = b"NUP\x01"
TOC_MAGIC = b"TOC\x01"
HEADER_SIZE, PKG_SIZE, DIR_SIZE, FILE_SIZE = 128, 64, 24, 80
EXTENT_ALIGN = 16
ABSENT = 0xFFFFFFFF
CODEC_RAW, CODEC_ZSTD = 0, 1
KIND_BASE, KIND_UPDATE, KIND_ADDON = 0, 1, 2
KIND_NAMES = {0: "base", 1: "update", 2: "addon", 3: "addon_update", 4: "system"}
PKG_FLAG_STANDALONE_UPDATE = 1
TLV_NPDM, TLV_NACP, TLV_ICON = 1, 2, 3
TLV_DISPLAY_VERSION, TLV_TITLE_NAME, TLV_PUBLISHER = 4, 5, 6
TLV_BUILD_ID, TLV_SOURCE_DUMP, TLV_LOCALIZED_TITLES, TLV_LOCALIZED_ICONS = 7, 8, 9, 10

_super_s = struct.Struct("<4sHHQQ32sQQII16s32x")
_toc_head_s = struct.Struct("<4sIQQQQQ")
_pkg_s = struct.Struct("<QIIIIBBHIQI20x")
_dir_s = struct.Struct("<IIII8x")
_file_s = struct.Struct("<IIQQQ32sBBH12x")


class NupError(ValueError):
    """A container violates a supported format or safety constraint."""


def aligned(value):
    return (value + EXTENT_ALIGN - 1) // EXTENT_ALIGN * EXTENT_ALIGN


def pack_super(*values):
    return _super_s.pack(*values)


@dataclass
class Package:
    title_id: int
    root_dir: int
    exefs_dir: int
    romfs_dir: int
    version: int
    kind: int
    flags: int
    meta_offset: int = 0
    meta_size: int = 0
    index: int = 0

    @property
    def kind_name(self):
        return KIND_NAMES[self.kind]

    @property
    def version_str(self):
        return f"{self.version >> 16}.{(self.version >> 8) & 255}.{self.version & 255}"
