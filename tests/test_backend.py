import hashlib
import json
import random
import shutil
import struct
import tempfile
import unittest
from pathlib import Path

from nup_core import format as F
from nup_core.access import app_meta, extract_tree, localized_icons, localized_titles
from nup_core.verify import verify as core_verify

from ns2_nup_tool.backend import Cancelled, run_operation, safe_name
from ns2_nup_tool.streaming import open_container
from ns2_nup_tool.worker import run_job
from tests.fixtures import PNG, TITLE_ID, make_dump


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ns2-nup-tool-tests-")
        self.root = Path(self.temp.name)
        self.source = self.root / "Synthetic dump 日本語"
        self.contents = make_dump(self.source)
        self.output = self.root / "game.nup"
        self.icon = self.root / "icon.png"
        self.icon.write_bytes(PNG)

    def tearDown(self):
        self.temp.cleanup()

    def run_op(self, operation, **kwargs):
        request = {"operation": operation, "source": str(self.source),
                   "output": str(self.output), "file": str(self.output), **kwargs}
        return run_operation(request, lambda: None, lambda *args: None)

    def test_pack_roundtrip_and_format_verification(self):
        result = self.run_op("pack", name="Synthetic Game", publisher="Test publisher",
                             display_version="1.2.3", icon=str(self.icon),
                             lang_names={"ja": "テスト"}, lang_icons={"ja": str(self.icon)})
        self.assertTrue(result["verification"]["ok"])
        self.assertEqual(result["packages"], 3)
        self.assertTrue(core_verify(str(self.output), deep=True)[0])
        with open_container(self.output) as reader:
            self.assertEqual(reader.packages[0].title_id, TITLE_ID)
            self.assertEqual(reader.packages[1].version, 458752)
            self.assertEqual(localized_titles(reader, reader.packages[0]), {b"ja": "テスト".encode()})
            self.assertEqual(localized_icons(reader, reader.packages[0]), {b"ja": PNG})
            self.assertIn(F.CODEC_RAW, [f[5] for f in reader.files])
            self.assertIn(F.CODEC_ZSTD, [f[5] for f in reader.files])
            self.assertNotIn(b".listing", [f[0] for f in reader.files])
            duplicates = [f for f in reader.files if f[0] == b"repeated.bin"]
            self.assertEqual(duplicates[0][3:5], duplicates[1][3:5])
            destination = self.root / "core-extracted"
            extract_tree(reader, str(destination), reader.packages[0].root_dir)
            self.assertEqual((destination / "romfs/data/raw.bin").read_bytes(), self.contents["base/romfs/data/raw.bin"])
        result = self.run_op("extract", package=2, output=str(self.root / "addon"))
        self.assertEqual(result["files"], 1)
        self.assertEqual((self.root / "addon/romfs/addon.bin").read_bytes(), self.contents["dlc/040074a01bf13001/0/romfs/addon.bin"])

    def test_deterministic_output(self):
        self.run_op("pack")
        second = self.root / "second.nup"
        self.run_op("pack", output=str(second))
        self.assertEqual(self.output.read_bytes(), second.read_bytes())

    def test_multichunk_raw_and_compressed_payloads(self):
        directory = self.source / "base/romfs"
        generator = random.Random(100)
        raw = directory / "multichunk-raw.bin"
        compressed = directory / "multichunk-compressed.bin"
        with raw.open("wb") as output, compressed.open("wb") as zeros:
            for _ in range(10):
                block = generator.randbytes(1024 * 1024)
                output.write(block)
                zeros.write(bytes(len(block)))
            output.write(b"partial chunk")
            zeros.write(b"partial chunk")
        self.run_op("pack")
        self.assertTrue(core_verify(str(self.output), deep=True)[0])
        destination = self.root / "multichunk"
        self.run_op("extract", output=str(destination), subtree="romfs")
        for original in (raw, compressed):
            with original.open("rb") as source, (destination / original.name).open("rb") as extracted:
                self.assertEqual(hashlib.file_digest(source, "sha256").digest(),
                                 hashlib.file_digest(extracted, "sha256").digest())

    def test_scan_reports_skipped_entries(self):
        unknown = self.source / "dlc/not-a-title/0/romfs/ignored"
        unknown.parent.mkdir(parents=True)
        unknown.write_bytes(b"must not be silently omitted")
        result = self.run_op("scan")
        self.assertEqual(len(result["packages"]), 3)
        self.assertTrue(any("not-a-title" in warning for warning in result["warnings"]))
        self.assertEqual(result["files"], 8)
        with self.assertRaisesRegex(ValueError, "cannot be assigned"):
            self.run_op("pack")

    def test_keep_listings_and_title_override(self):
        self.run_op("pack", keep_listings=True, title_id="0100000000002222")
        with open_container(self.output) as reader:
            self.assertIn(b".listing", [f[0] for f in reader.files])
            self.assertEqual(reader.packages[0].title_id, 0x0100000000002222)
            self.assertEqual(reader.packages[2].title_id, 0x040074A01BF13001)

    def test_bare_and_update_only(self):
        self.run_op("pack", source=str(self.source / "base"))
        standalone = self.root / "standalone"
        shutil.copytree(self.source / "updates", standalone / "updates")
        result = self.run_op("scan", source=str(standalone))
        self.assertTrue(result["packages"][0]["standalone"])
        other = self.root / "update.nup"
        self.run_op("pack", source=str(standalone), output=str(other), title_id="0100000000001000")
        with open_container(other) as reader:
            self.assertEqual(reader.packages[0].flags, F.PKG_FLAG_STANDALONE_UPDATE)

    def test_edit_copy_and_inplace_preserve_content_and_identity(self):
        self.run_op("pack", name="Before", publisher="Keep publisher", lang_names={"ja": "Before"})
        original = self.output.read_bytes()
        with open_container(self.output) as reader:
            uuid = reader.super["uuid"]
            files = list(reader.files)
            identity_meta = app_meta(reader, reader.packages[0])[F.TLV_NPDM]
        copy = self.root / "edited.nup"
        self.run_op("edit", package=0, output=str(copy), name="After", lang_names={"ja": "", "fr": "Essai"})
        self.assertEqual(original, self.output.read_bytes())
        self.assertTrue(core_verify(str(copy), deep=True)[0])
        with open_container(copy) as reader:
            self.assertEqual(reader.files, files)
            self.assertEqual(reader.super["uuid"], uuid)
            meta = app_meta(reader, reader.packages[0])
            self.assertEqual(meta[F.TLV_NPDM], identity_meta)
            self.assertEqual(meta[F.TLV_PUBLISHER], b"Keep publisher")
            self.assertEqual(meta[F.TLV_TITLE_NAME], b"After")
            self.assertEqual(localized_titles(reader, reader.packages[0]), {b"fr": b"Essai"})
        self.run_op("edit", inplace=True, package=2, name="DLC name")
        self.run_op("edit", inplace=True, package=0, clear_name=True)
        with open_container(self.output) as reader:
            self.assertNotIn(F.TLV_TITLE_NAME, app_meta(reader, reader.packages[0]))
            self.assertEqual(app_meta(reader, reader.packages[2])[F.TLV_TITLE_NAME], b"DLC name")

    def test_icon_set_clear_and_localized_removal(self):
        self.run_op("pack", icon=str(self.icon), lang_icons={"ja": str(self.icon)})
        self.run_op("edit", inplace=True, package=0, clear_icon=True, lang_icons={"ja": "", "en": str(self.icon)})
        with open_container(self.output) as reader:
            self.assertNotIn(F.TLV_ICON, app_meta(reader, reader.packages[0]))
            self.assertEqual(localized_icons(reader, reader.packages[0]), {b"en": PNG})

    def test_existing_output_and_nested_output_rejected(self):
        self.output.write_bytes(b"preserve me")
        with self.assertRaises(ValueError):
            self.run_op("pack")
        self.assertEqual(self.output.read_bytes(), b"preserve me")
        with self.assertRaises(ValueError):
            self.run_op("pack", output=str(self.source / "bad.nup"))

    def test_invalid_source_and_options(self):
        for arguments in ({"title_id": "123"}, {"level": 23}, {"lang_names": {"日本": "bad"}},
                          {"icon": str(self.root / "missing.png")}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                self.run_op("pack", **arguments)
        invalid = self.root / "encrypted"
        invalid.mkdir()
        (invalid / "game.nsp").write_bytes(b"placeholder")
        with self.assertRaises(SystemExit):
            self.run_op("scan", source=str(invalid))

    def test_cancelled_pack_publishes_nothing(self):
        def report(done, total, message):
            if message.startswith("Compressing"):
                raise Cancelled()
        with self.assertRaises(Cancelled):
            run_operation({"operation": "pack", "source": str(self.source), "output": str(self.output)},
                          lambda: None, report)
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob(".ns2-nup-tool-*")))

    def test_cancelled_edit_preserves_original(self):
        self.run_op("pack")
        original = self.output.read_bytes()
        def report(*args):
            raise Cancelled()
        with self.assertRaises(Cancelled):
            run_operation({"operation": "edit", "file": str(self.output), "inplace": True, "name": "Changed"},
                          lambda: None, report)
        self.assertEqual(original, self.output.read_bytes())
        self.assertFalse(list(self.root.glob(".nup-edit-*")))

    def test_corruption_distinguishes_fast_and_deep(self):
        self.run_op("pack")
        with open_container(self.output) as reader:
            raw = next(f for f in reader.files if f[0] == b"raw.bin")
        with self.output.open("r+b") as file:
            file.seek(raw[3])
            byte = file.read(1)
            file.seek(raw[3])
            file.write(bytes([byte[0] ^ 0xFF]))
        self.assertTrue(self.run_op("verify", deep=False)["ok"])
        self.assertFalse(self.run_op("verify", deep=True)["ok"])
        with self.assertRaises(ValueError):
            self.run_op("extract", output=str(self.root / "broken-extract"))
        self.assertFalse((self.root / "broken-extract").exists())

    def test_inspect_and_subtree_extraction(self):
        self.run_op("pack")
        result = self.run_op("inspect")
        self.assertEqual(result["packages"][0]["build_id"], bytes(range(32)).hex().upper())
        destination = self.root / "subtree"
        self.run_op("extract", output=str(destination), subtree="romfs/data")
        self.assertTrue((destination / "raw.bin").is_file())
        self.assertFalse((destination / "romfs").exists())
        self.assertTrue(self.run_op("verify", deep=True)["ok"])

    def test_extract_refuses_existing_folder(self):
        self.run_op("pack")
        existing = self.root / "existing"
        existing.mkdir()
        sentinel = existing / "keep"
        sentinel.write_text("unchanged")
        with self.assertRaises(ValueError):
            self.run_op("extract", output=str(existing))
        self.assertEqual(sentinel.read_text(), "unchanged")

    def test_unsafe_windows_names(self):
        for name in (b"../escape", b"C:escape", b"\\absolute", b"CON", b"lpt1.txt", b"trailing.", b"..", b""):
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_name(name)
        self.assertEqual(safe_name("日本語.txt".encode()), "日本語.txt")

    def test_malformed_child_is_rejected_before_traversal(self):
        self.run_op("pack")
        with open_container(self.output) as reader:
            header = dict(reader.super)
            slot = F._toc_head_s.size + len(reader.packages) * F.PKG_SIZE + reader.dir_count * F.DIR_SIZE + reader.file_count * F.FILE_SIZE
        data = bytearray(self.output.read_bytes())
        struct.pack_into("<I", data, header["toc_offset"] + slot, 0xFFFFFFFF)
        data[0x18:0x38] = hashlib.sha256(data[header["toc_offset"]:header["toc_offset"] + header["toc_size"]]).digest()
        self.output.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "outside"):
            self.run_op("inspect")

    def test_worker_reports_invalid_input_and_cancellation(self):
        job = self.root / "job"
        job.mkdir()
        request = {"operation": "pack", "source": str(self.source), "output": str(self.output)}
        (job / "request.json").write_text(json.dumps(request))
        (job / "cancel").touch()
        self.assertEqual(run_job(job), 1)
        self.assertEqual(json.loads((job / "result.json").read_text())["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
