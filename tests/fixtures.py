"""Synthetic content only; no console software or keys are used in tests."""

import random
import struct
import zlib
from pathlib import Path

TITLE_ID = 0x0100000000001000


def make_npdm(version=0, title_id=TITLE_ID):
    data = bytearray(0x80)
    data[:4] = b"META"
    struct.pack_into("<I", data, 0x18, version)
    return bytes(data) + b"ACI0" + bytes(12) + struct.pack("<Q", title_id)


def make_program(seed):
    return b"NSO0" + bytes(60) + bytes([seed]) * 32 + bytes([seed]) * 500


def add_update_program(root, seed, version, title_id=TITLE_ID):
    exefs = root / "exefs"
    exefs.mkdir(parents=True, exist_ok=True)
    (exefs / "main").write_bytes(make_program(seed))
    (exefs / "main.npdm").write_bytes(make_npdm(version, title_id))
    (exefs / "sdk").write_bytes(b"matching sdk" + bytes([seed]))


def make_flat_dump(root, version=0):
    for kind in ("base", "updates"):
        (root / kind / "exefs").mkdir(parents=True)
        (root / kind / "exefs/main.npdm").write_bytes(make_npdm(version if kind == "updates" else 0))
    (root / "updates/romfs").mkdir()
    (root / "updates/romfs/update.bin").write_bytes(b"This update must not disappear" * 100)

def png_chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


PNG = (b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
       + png_chunk(b"IDAT", zlib.compress(b"\0\x47\xd7\xf0")) + png_chunk(b"IEND", b""))


def make_nacp(names=None, publisher="Test publisher", version="1.2.3", compressed=False):
    names = names or {0: "Test game", 2: "テスト"}
    data = bytearray(0x4000)
    titles = bytearray((18 if compressed else 16) * 0x300)
    for index, name in names.items():
        text = name.encode("utf-8")
        vendor = publisher.encode("utf-8")
        offset = index * 0x300
        titles[offset:offset + len(text)] = text
        titles[offset + 0x200:offset + 0x200 + len(vendor)] = vendor
    if compressed:
        compressor = zlib.compressobj(wbits=-15)
        payload = compressor.compress(titles) + compressor.flush()
        struct.pack_into("<H", data, 0, len(payload))
        data[2:2 + len(payload)] = payload
        data[0x3215] = 1
    else:
        data[:len(titles)] = titles
    data[0x3060:0x3060 + len(version)] = version.encode("ascii")
    return bytes(data)


def make_dump(root):
    root = Path(root)
    content = {
        "base/exefs/main": b"NSO0" + bytes(60) + bytes(range(32)) + b"synthetic program" * 100,
        "base/exefs/main.npdm": b"ACI0" + bytes(12) + struct.pack("<Q", TITLE_ID),
        "base/romfs/data/repeated.bin": b"sample content\n" * 10000,
        "base/romfs/data/raw.bin": random.Random(42).randbytes(12000),
        "base/romfs/empty": b"",
        "base/romfs/日本語.txt": "Synthetic Unicode content".encode(),
        "base/romfs/.listing": b"listing artifact",
        "updates/458752/romfs/data/repeated.bin": b"sample content\n" * 10000,
        "dlc/040074a01bf13001/0/romfs/addon.bin": b"synthetic add-on" * 100,
    }
    for relative, data in content.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return content
