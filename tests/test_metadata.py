import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from ns2_nup_tool.backend import run_operation
from ns2_nup_tool.dump_metadata import parse_nacp, report_header, title_bytes
from tests.fixtures import PNG, TITLE_ID, make_dump, make_nacp


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "Example game"
        make_dump(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def scan(self):
        return run_operation({"operation": "scan", "source": str(self.root)}, lambda: None, lambda *args: None)["metadata"]

    def test_nacp_reads_original_titles_publisher_and_version(self):
        path = self.root / "base/control.nacp"
        path.write_bytes(make_nacp())
        parsed = parse_nacp(path)
        self.assertEqual(parsed["name"], "Test game")
        self.assertEqual(parsed["publisher"], "Test publisher")
        self.assertEqual(parsed["display_version"], "1.2.3")
        self.assertEqual(parsed["lang_names"]["ja"], "テスト")

    def test_compressed_extended_language_titles(self):
        path = self.root / "control.nacp"
        path.write_bytes(make_nacp({0: "English", 16: "Polski", 17: "ไทย"}, compressed=True))
        parsed = parse_nacp(path)
        self.assertEqual(parsed["lang_names"], {"en-us": "English", "pl": "Polski", "th": "ไทย"})

    def test_rejects_bad_sizes_unknown_formats_and_decompression_bombs(self):
        path = self.root / "control.nacp"
        path.write_bytes(b"not a control file")
        with self.assertRaises(ValueError):
            parse_nacp(path)
        invalid = bytearray(make_nacp())
        invalid[0x3215] = 7
        with self.assertRaises(ValueError):
            title_bytes(invalid)
        compressor = zlib.compressobj(wbits=-15)
        payload = compressor.compress(bytes(1024 * 1024)) + compressor.flush()
        struct.pack_into("<H", invalid, 0, len(payload))
        invalid[2:2 + len(payload)] = payload
        invalid[0x3215] = 1
        with self.assertRaises(ValueError):
            title_bytes(invalid)

    def test_latest_update_wins_and_icons_are_discovered(self):
        (self.root / "base/control.nacp").write_bytes(make_nacp({0: "Base"}, version="1.0.0"))
        control = self.root / "updates/458752/control"
        control.mkdir()
        (control / "control.nacp").write_bytes(make_nacp({0: "Updated"}, version="2.0.0"))
        (control / "icon_AmericanEnglish.dat").write_bytes(PNG)
        metadata = self.scan()
        self.assertEqual(metadata["values"]["name"], "Updated")
        self.assertEqual(metadata["values"]["display_version"], "V458752")
        self.assertEqual(metadata["values"]["title_id"], f"{TITLE_ID:016X}")
        self.assertEqual(metadata["values"]["icon"], str(control / "icon_AmericanEnglish.dat"))
        self.assertEqual(metadata["missing"], [])

    def test_folder_suggestion_and_snapshot_report_are_not_original_metadata(self):
        report = self.root / "game.nsp.report.json"
        header = {"app": "NSP Box", "title_id": f"{TITLE_ID:016x}", "original_control_preserved": False,
                  "display_version": "Snapshot", "title": "Misleading title", "files": ["x" * 100000]}
        report.write_text(json.dumps(header), encoding="utf-8")
        self.assertNotIn("files", report_header(report))
        metadata = self.scan()
        self.assertEqual(metadata["values"]["name"], "Example game")
        self.assertEqual(metadata["suggested"], ["name"])
        self.assertEqual(metadata["values"]["display_version"], "V458752")
        self.assertNotIn("publisher", metadata["values"])
        self.assertTrue(any("not preserved" in notice for notice in metadata["notices"]))

    def test_corrupt_control_is_a_notice_and_does_not_stop_scanning(self):
        (self.root / "base/control.nacp").write_bytes(b"broken")
        result = self.scan()
        self.assertTrue(any("16 KiB" in notice for notice in result["notices"]))
        self.assertIn("title_id", result["values"])

    def test_base_only_uses_v0_even_when_control_has_a_marketing_version(self):
        base = self.root / "base"
        (base / "control.nacp").write_bytes(make_nacp(version="1.2.3"))
        request = {"source": str(base)}
        scan = run_operation({"operation": "scan", **request}, lambda: None, lambda *args: None)
        self.assertEqual(scan["metadata"]["values"]["display_version"], "V0")
        output = self.root / "base-only.nup"
        run_operation({"operation": "pack", "output": str(output), **request}, lambda: None, lambda *args: None)
        packed = run_operation({"operation": "inspect", "file": str(output)}, lambda: None, lambda *args: None)
        self.assertEqual(packed["packages"][0]["display_version"], "V0")
