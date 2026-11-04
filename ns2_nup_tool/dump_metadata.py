"""Read application metadata from decrypted control files, without guessing IDs.

NACP offsets and language order: https://switchbrew.org/wiki/NACP
Format 0 stores 16 titles; format 1 uses bounded Deflate data and can include
Polish/Thai. No encryption, online lookup, or filename-derived identity is used.
"""

from __future__ import annotations

import struct
import zlib
import json
from pathlib import Path

from nup_core import format as F, meta as M
from nup_core.discover import parse_npdm_program_id

LANGUAGES = (
    ("AmericanEnglish", "en-us"), ("BritishEnglish", "en-gb"), ("Japanese", "ja"),
    ("French", "fr"), ("German", "de"), ("LatinAmericanSpanish", "es-419"),
    ("Spanish", "es-es"), ("Italian", "it"), ("Dutch", "nl"),
    ("CanadianFrench", "fr-ca"), ("Portuguese", "pt-pt"), ("Russian", "ru"),
    ("Korean", "ko"), ("TraditionalChinese", "zh-hant"), ("SimplifiedChinese", "zh-hans"),
    ("BrazilianPortuguese", "pt-br"), ("Polish", "pl"), ("Thai", "th"),
)
ICON_LANGUAGES = {name.casefold(): tag for name, tag in LANGUAGES}
METADATA_DIRS = ("", "control", "control/romfs", "romfs", "exefs", "metadata", "meta")


def text_field(data):
    value = data.split(b"\0", 1)[0].decode("utf-8", "strict").strip()
    if any(ord(char) < 32 for char in value):
        raise ValueError("A metadata string contains control characters.")
    return value


def title_bytes(data):
    data_format = data[0x3215]
    if data_format == 0:
        return data[:0x3000]
    if data_format != 1:
        raise ValueError(f"Unsupported NACP title format {data_format}.")
    length = struct.unpack_from("<H", data)[0]
    if not 0 < length <= 0x2FFE:
        raise ValueError("Invalid compressed NACP title length.")
    payload = data[2:2 + length]
    limit = len(LANGUAGES) * 0x300
    for window_bits in (-15, 15):
        try:
            decoder = zlib.decompressobj(window_bits)
            titles = decoder.decompress(payload, limit + 1)
            if (len(titles) > limit or not decoder.eof or decoder.unused_data
                    or not titles or len(titles) % 0x300):
                continue
            return titles
        except zlib.error:
            continue
    raise ValueError("Invalid or oversized compressed NACP titles.")


def parse_nacp(path):
    path = Path(path)
    if path.stat().st_size != 0x4000:
        raise ValueError("Expected a 16 KiB decrypted control.nacp.")
    data = path.read_bytes()
    titles = title_bytes(data)
    names, publishers = {}, {}
    for index, (_, language) in enumerate(LANGUAGES[:len(titles) // 0x300]):
        entry = titles[index * 0x300:(index + 1) * 0x300]
        name, publisher = text_field(entry[:0x200]), text_field(entry[0x200:])
        if name:
            names[language] = name
        if publisher:
            publishers[language] = publisher
    preferred = next(iter(names), next(iter(publishers), "en-us"))
    return {"name": names.get(preferred, ""), "publisher": publishers.get(preferred, ""),
            "display_version": text_field(data[0x3060:0x3070]),
            "lang_names": names, "preferred_language": preferred}


def image_file(path):
    if not 0 < path.stat().st_size <= 32 * 1024 * 1024:
        return False
    with path.open("rb") as file:
        header = file.read(8)
    return header.startswith(b"\xff\xd8\xff") or header == b"\x89PNG\r\n\x1a\n"


def report_header(path):
    """Read scalar report fields without allocating the potentially huge file list."""
    with path.open("rb") as file:
        text = file.read(64 * 1024).decode("utf-8-sig")
    decoder, fields = json.JSONDecoder(), {}
    offset = text.index("{") + 1
    while offset < len(text):
        while offset < len(text) and text[offset] in " \r\n\t,":
            offset += 1
        if offset >= len(text) or text[offset] == "}":
            break
        key, offset = decoder.raw_decode(text, offset)
        while offset < len(text) and text[offset].isspace():
            offset += 1
        if offset >= len(text) or text[offset] != ":":
            break
        offset += 1
        while offset < len(text) and text[offset].isspace():
            offset += 1
        if key == "files":
            break
        value, offset = decoder.raw_decode(text, offset)
        if isinstance(value, (str, bool, int, float)) or value is None:
            fields[key] = value
    return fields


def report_notices(source, identity, check):
    parents = [Path(source)]
    for folder in (Path(source) / "updates", Path(source) / "base"):
        if folder.is_dir():
            parents.append(folder)
            if folder.name == "updates":
                parents.extend(p for p in folder.iterdir() if p.is_dir() and not p.is_symlink() and not p.is_junction())
    notices = []
    for parent in parents:
        for report in parent.glob("*.report.json"):
            check()
            if report.is_symlink():
                continue
            try:
                header = report_header(report)
            except (OSError, ValueError, UnicodeError):
                continue
            if header.get("app") != "NSP Box" or header.get("title_id", "").lower() != f"{identity.title_id:016x}":
                continue
            if header.get("original_control_preserved") is False:
                notices.append(f"NSP Box reports that original control metadata was not preserved ({report.name}). "
                               "Its snapshot label is not used as the game's original display version.")
    return notices


def discover_metadata(source, packages, check):
    result = {"values": {}, "sources": {}, "notices": [], "missing": []}
    values, sources = result["values"], result["sources"]
    identity = next((p for p in packages if p.kind == F.KIND_BASE), packages[0])
    if hasattr(identity, "bundle_metadata"):
        saved = M.parse_block(identity.bundle_metadata)
        for field, tag in (("name", F.TLV_TITLE_NAME), ("publisher", F.TLV_PUBLISHER)):
            if saved.get(tag):
                values[field] = saved[tag].decode("utf-8", "replace")
                sources[field] = "Original NUP metadata"
        if identity.title_id:
            values["title_id"] = f"{identity.title_id:016X}"
            sources["title_id"] = "Original NUP package identity"
        if Path(identity.bundle_icon).is_file():
            values["icon"] = identity.bundle_icon
            sources["icon"] = "Original NUP metadata"
    # Newest update metadata wins; bundle-level control is next, then the base.
    updates = sorted((p for p in packages if p.kind == F.KIND_UPDATE), key=lambda p: p.version, reverse=True)
    defaulted = bool(updates) and updates[0].version == 0
    values["display_version"] = f"V{updates[0].version if updates else 0}"
    sources["display_version"] = ("Update version unavailable or set to 0; V0 placeholder" if defaulted else
                                  f"Newest included update: {updates[0].src}" if updates else "No update package included (V0)")
    roots = [Path(p.src) for p in updates] + [Path(source)]
    roots += [Path(p.src) for p in packages if p.kind == F.KIND_BASE]
    visited = set()
    default_icon = None
    preferred = "en-us"
    for root in roots:
        for relative in METADATA_DIRS:
            check()
            directory = root / relative
            if directory in visited or not directory.is_dir() or directory.is_symlink() or directory.is_junction():
                continue
            visited.add(directory)
            for path in sorted(directory.iterdir(), key=lambda p: (p.name.lower() != "control.nacp", p.name.lower())):
                check()
                if not path.is_file() or path.is_symlink():
                    continue
                lower = path.name.casefold()
                if path.suffix.casefold() == ".nacp":
                    try:
                        detected = parse_nacp(path)
                    except (ValueError, OSError, UnicodeError) as error:
                        result["notices"].append(f"Could not read {path.name}: {error}")
                        continue
                    for key in ("name", "publisher", "display_version"):
                        if detected[key] and key not in values:
                            values[key] = detected[key]
                            sources[key] = str(path)
                    if detected["lang_names"] and "lang_names" not in values:
                        values["lang_names"] = detected["lang_names"]
                        sources["lang_names"] = str(path)
                        preferred = detected["preferred_language"]
                elif lower.startswith("icon_") and path.suffix.lower() in (".dat", ".jpg", ".jpeg", ".png"):
                    language = ICON_LANGUAGES.get(path.stem[5:].casefold())
                    if language and image_file(path):
                        values.setdefault("lang_icons", {}).setdefault(language, str(path))
                elif lower in ("icon.dat", "icon.jpg", "icon.jpeg", "icon.png"):
                    if default_icon is None and image_file(path):
                        default_icon = str(path)
    icons = values.get("lang_icons", {})
    icon = icons.get(preferred) or icons.get("en-us") or default_icon or next(iter(icons.values()), None)
    if icon and "icon" not in values:
        values["icon"] = icon
        sources["icon"] = icon
    identity = next((p for p in packages if p.kind == F.KIND_BASE), packages[0])
    program_id = parse_npdm_program_id(identity.npdm) if identity.npdm else None
    if program_id and "title_id" not in values:
        values["title_id"] = f"{program_id:016X}"
        npdm_path = Path(identity.src) / "exefs/main.npdm"
        sources["title_id"] = str(npdm_path if npdm_path.exists() else Path(identity.src) / "main.npdm")
    if identity.build_id:
        values["build_id"] = identity.build_id.hex().upper()
        sources["build_id"] = str(Path(identity.src) / "exefs/main")
    result["notices"].extend(report_notices(source, identity, check))
    folder_name = Path(source).name
    if "name" not in values and folder_name.lower() not in ("base", "updates", "dump", "exefs", "romfs") and not folder_name.isdecimal():
        values["name"] = folder_name
        sources["name"] = f"Folder name suggestion: {source}"
        result["notices"].append("Game name suggested from the selected folder name; original control title was not found.")
        result["suggested"] = ["name"]
    result["missing"] = [name for name in ("title_id", "name", "publisher", "display_version", "icon") if not values.get(name)]
    return result
