"""Bounded TLV and localized metadata encoding, independent of payload storage."""

from pathlib import Path
import struct

from . import format as F

_TLV = struct.Struct("<HHI")


def parse_block(block):
    records, cursor = {}, 0
    while cursor < len(block):
        if len(block) - cursor < _TLV.size:
            raise F.NupError("Truncated metadata record header")
        tag, reserved, length = _TLV.unpack_from(block, cursor)
        cursor += _TLV.size
        if reserved or length > len(block) - cursor or tag in records:
            raise F.NupError("Invalid or duplicate metadata record")
        records[tag] = bytes(block[cursor:cursor + length])
        cursor += length
    return records


def serialize_block(records):
    return b"".join(_TLV.pack(tag, 0, len(value)) + value for tag, value in sorted(records.items()))


def decode_localized(data):
    entries, cursor = {}, 0
    while cursor < len(data):
        length = data[cursor]
        cursor += 1
        if not length or cursor + length + 4 > len(data):
            raise F.NupError("Invalid localized metadata language")
        language = data[cursor:cursor + length].lower()
        try:
            language.decode("ascii")
        except UnicodeError as error:
            raise F.NupError("Non-ASCII language tag") from error
        cursor += length
        size = struct.unpack_from("<I", data, cursor)[0]
        cursor += 4
        if size > len(data) - cursor or language in entries:
            raise F.NupError("Truncated or duplicate localized metadata")
        entries[language] = bytes(data[cursor:cursor + size])
        cursor += size
    return entries


def encode_localized(entries):
    normalized = {}
    for language, value in entries.items():
        key = language.encode("ascii") if isinstance(language, str) else language
        key = key.lower()
        if not 1 <= len(key) <= 255 or key in normalized:
            raise F.NupError("Invalid or duplicate language tag")
        normalized[key] = value
    return b"".join(bytes([len(key)]) + key + struct.pack("<I", len(value)) + value
                    for key, value in sorted(normalized.items()))


def merge_app_meta(records, *, name=None, publisher=None, display_version=None, icon=None,
                   lang_names=None, lang_icons=None, clear_name=False, clear_publisher=False,
                   clear_display_version=False, clear_icon=False):
    result = dict(records)
    for tag, value, clear in ((F.TLV_TITLE_NAME, name, clear_name),
                              (F.TLV_PUBLISHER, publisher, clear_publisher),
                              (F.TLV_DISPLAY_VERSION, display_version, clear_display_version),
                              (F.TLV_ICON, icon, clear_icon)):
        if clear:
            result.pop(tag, None)
        elif value is not None:
            result[tag] = Path(value).read_bytes() if tag == F.TLV_ICON else value.encode("utf-8")
    for tag, changes in ((F.TLV_LOCALIZED_TITLES, lang_names), (F.TLV_LOCALIZED_ICONS, lang_icons)):
        if changes is None:
            continue
        current = decode_localized(result.get(tag, b""))
        for language, value in changes.items():
            key = language.encode("ascii").lower() if isinstance(language, str) else language.lower()
            if value:
                current[key] = Path(value).read_bytes() if tag == F.TLV_LOCALIZED_ICONS else value.encode("utf-8")
            else:
                current.pop(key, None)
        if current:
            result[tag] = encode_localized(current)
        else:
            result.pop(tag, None)
    return result


def meta_block(package, names, icons, publisher, display_version, include_app, source_name):
    records = {F.TLV_SOURCE_DUMP: source_name.encode("utf-8")}
    if package.npdm:
        records[F.TLV_NPDM] = package.npdm
    if package.build_id:
        records[F.TLV_BUILD_ID] = package.build_id
    if include_app:
        records = merge_app_meta(records, name=names.get(None), icon=icons.get(None),
                                 publisher=publisher, display_version=display_version,
                                 lang_names={k: v for k, v in names.items() if k is not None},
                                 lang_icons={k: v for k, v in icons.items() if k is not None})
    return serialize_block(records)
