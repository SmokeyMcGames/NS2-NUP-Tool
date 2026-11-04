"""A direct updates/ directory must be visible and included by the packer."""

import tempfile
import base64
import unittest
from unittest.mock import patch
from pathlib import Path

from nup_core.verify import verify
from ns2_nup_tool.backend import Cancelled, run_operation
from tests.fixtures import PNG, TITLE_ID, make_flat_dump, make_npdm


class DirectUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.dump = self.root / "game"
        self.output = self.root / "game.nup"
        make_flat_dump(self.dump)

    def tearDown(self):
        self.temp.cleanup()

    def call(self, operation, **options):
        return run_operation({"operation": operation, "source": str(self.dump), "output": str(self.output),
                              "file": str(self.output), **options}, lambda: None, lambda *args: None)

    def test_unknown_direct_update_defaults_to_zero_and_is_packed_with_warning(self):
        result = self.call("scan")
        self.assertEqual([p["kind"] for p in result["packages"]], ["base", "update"])
        self.assertEqual(result["packages"][1]["version"], 0)
        self.assertEqual(result["files"], 3)
        self.assertTrue(result["version_defaulted"])
        self.assertIn("V0", result["warnings"][0])
        self.assertEqual(result["metadata"]["values"]["display_version"], "V0")
        self.assertIn("updates/0/", result["layout_repairs"][0])
        self.assertTrue((self.dump / "updates/romfs/update.bin").is_file())
        self.assertFalse((self.dump / "updates/0").exists())
        packed = self.call("pack", update_version="0")
        self.assertIn("V0", packed["warnings"][0])
        info = self.call("inspect")
        self.assertEqual([p["kind"] for p in info["packages"]], ["base", "update"])
        self.assertEqual(info["packages"][1]["version"], 0)
        self.assertEqual(info["packages"][0]["display_version"], "V0")
        self.assertTrue(verify(str(self.output), deep=True)[0])
        destination = self.root / "extracted"
        self.call("extract", package=1, output=str(destination))
        self.assertEqual((destination / "romfs/update.bin").read_bytes(), (self.dump / "updates/0/romfs/update.bin").read_bytes())
        self.assertFalse((self.dump / "updates/exefs").exists())
        self.assertFalse((self.dump / "updates/romfs").exists())
        self.assertEqual(self.call("scan")["layout_repairs"], [])

    def test_npdm_version_is_detected_and_actual_update_is_packed(self):
        (self.dump / "updates/exefs/main.npdm").write_bytes(make_npdm(65536))
        result = self.call("scan")
        self.assertEqual(result["packages"][1]["version"], 65536)
        self.assertEqual(result["metadata"]["values"]["display_version"], "V65536")
        self.call("pack")
        info = self.call("inspect")
        self.assertEqual([p["kind"] for p in info["packages"]], ["base", "update"])
        self.assertEqual(info["packages"][1]["version"], 65536)
        self.assertTrue(verify(str(self.output), deep=True)[0])
        destination = self.root / "extracted"
        self.call("extract", package=1, output=str(destination))
        self.assertEqual((destination / "romfs/update.bin").read_bytes(), (self.dump / "updates/65536/romfs/update.bin").read_bytes())

    def test_explicit_version_and_standalone_direct_layout(self):
        (self.dump / "updates/exefs/main.npdm").write_bytes(make_npdm(65536))
        (self.dump / "updates/companion.txt").write_bytes(b"Preserve extra files")
        icon = self.dump / "updates/icon.png"
        icon.write_bytes(PNG)
        self.call("pack", update_version="131072", icon=str(icon), lang_icons={"en": str(icon)})
        info = self.call("inspect")
        self.assertEqual(info["packages"][1]["version"], 131072)
        self.assertEqual(base64.b64decode(info["packages"][0]["icon"]), PNG)
        self.assertIn("en", info["packages"][0]["lang_icons"])
        self.assertEqual((self.dump / "updates/131072/companion.txt").read_bytes(), b"Preserve extra files")
        self.assertFalse((self.dump / "updates/65536").exists())
        self.assertFalse(self.call("scan")["packages"][1]["flat_update"])
        source = self.root / "standalone"
        (source / "updates/romfs").mkdir(parents=True)
        (source / "updates/romfs/update.bin").write_bytes(b"standalone")
        result = self.call("scan", source=str(source), update_version="196608")
        self.assertTrue(result["packages"][0]["standalone"])
        self.assertEqual(result["packages"][0]["version"], 196608)

    def test_layout_is_restored_on_pack_failure_cancellation_or_publish_failure(self):
        original = {p.relative_to(self.dump).as_posix(): p.read_bytes() for p in self.dump.rglob("*") if p.is_file()}
        for operation, error in (("pack_streamed", OSError("write failed")),
                                 ("pack_streamed", Cancelled("cancelled")),
                                 ("publish_file", OSError("publish failed"))):
            def fail(*args, **kwargs):
                self.assertTrue((self.dump / "updates/131072/romfs/update.bin").is_file())
                raise error
            with self.subTest(operation=operation, error=str(error)), \
                    patch("ns2_nup_tool.backend." + operation, side_effect=fail), \
                    self.assertRaises(type(error)):
                self.call("pack", update_version="131072")
            self.assertFalse(self.output.exists())
            self.assertFalse(list(self.dump.glob(".nup-layout-*")))
            self.assertFalse((self.dump / "updates/131072").exists())
            self.assertEqual({p.relative_to(self.dump).as_posix(): p.read_bytes() for p in self.dump.rglob("*") if p.is_file()}, original)

    def test_existing_version_destination_is_not_overwritten(self):
        (self.dump / "updates/0").write_bytes(b"Keep this file")
        with self.assertRaisesRegex(ValueError, "Cannot correct"):
            self.call("pack")
        self.assertEqual((self.dump / "updates/0").read_bytes(), b"Keep this file")
        self.assertTrue((self.dump / "updates/romfs/update.bin").is_file())
        self.assertFalse(self.output.exists())

    def test_mismatched_game_and_overlapping_layout_are_rejected(self):
        (self.dump / "updates/exefs/main.npdm").write_bytes(make_npdm(65536, TITLE_ID + 1))
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.call("scan")
        (self.dump / "updates/65536/romfs").mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "mixes direct content"):
            self.call("scan")
