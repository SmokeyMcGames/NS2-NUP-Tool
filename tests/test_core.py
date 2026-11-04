"""Reader rejection tests that mutate valid synthetic containers at wire offsets."""

import hashlib
from pathlib import Path
import struct
import tempfile
import unittest

from nup_core import format as F, meta as M
from nup_core.read import NupReader
from ns2_nup_tool.backend import run_operation
from tests.fixtures import make_dump


class CoreValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        dump = self.root / "dump"
        make_dump(dump)
        self.file = self.root / "valid.nup"
        run_operation({"operation": "pack", "source": str(dump), "output": str(self.file)},
                      lambda: None, lambda *args: None)
        with NupReader(self.file) as reader:
            self.header = dict(reader.super)
            self.dirs = reader.dir_count
            self.files = reader.file_count
            self.packages = len(reader.packages)

    def tearDown(self):
        self.temp.cleanup()

    def corrupt(self, edit, rehash=True):
        data = bytearray(self.file.read_bytes())
        edit(data)
        if rehash:
            start = self.header["toc_offset"]
            data[24:56] = hashlib.sha256(data[start:start + self.header["toc_size"]]).digest()
        path = self.root / "corrupt.nup"
        path.write_bytes(data)
        with self.assertRaises(ValueError):
            with NupReader(path):
                pass
        path.unlink()  # Rejected readers must release Windows file/mapping handles.

    def test_writer_aligns_toc_and_uuid_is_identity_derived(self):
        self.assertEqual(self.header["toc_size"] % 16, 0)
        with NupReader(self.file) as reader:
            payload = b"".join(struct.pack("<QIB", p.title_id, p.version, p.kind) for p in reader.packages)
            self.assertEqual(self.header["uuid"], hashlib.sha256(payload).digest()[:16])

    def test_bad_header_and_toc_hash_are_rejected(self):
        for offset in (0, 64, 96, 128):
            with self.subTest(offset=offset):
                self.corrupt(lambda data: data.__setitem__(offset, data[offset] ^ 1), rehash=False)

    def test_huge_counts_and_bad_string_pool_are_rejected(self):
        for offset in (128 + 8, 128 + 24, 128 + 32):
            with self.subTest(offset=offset):
                self.corrupt(lambda data: struct.pack_into("<Q", data, offset, 2**63))

    def test_cycle_and_out_of_range_children_are_rejected(self):
        slot = 128 + 48 + self.packages * 64 + self.dirs * 24 + self.files * 80
        for child in (0, 0xFFFFFFFF):
            with self.subTest(child=child):
                self.corrupt(lambda data: struct.pack_into("<I", data, slot, child))

    def test_unsupported_codec_and_extent_overlap_are_rejected(self):
        file_offset = 128 + 48 + self.packages * 64 + self.dirs * 24
        self.corrupt(lambda data: data.__setitem__(file_offset + 64, 250))
        self.corrupt(lambda data: struct.pack_into("<Q", data, file_offset + 16, 128))

    def test_bad_metadata_and_localized_records_are_rejected(self):
        for payload in (b"short", struct.pack("<HHI", 5, 0, 400),
                        struct.pack("<HHI", 5, 0, 0) * 2):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                M.parse_block(payload)
        for payload in (b"\0", b"\x02en\xff\xff\xff\xff",
                        b"\x02en\0\0\0\0" * 2):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                M.decode_localized(payload)
