"""Replacing the base must use exactly the update's content and metadata."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nup_core import format as F, meta as M
from nup_core.access import app_meta, resolve_path
from nup_core.verify import verify

from ns2_nup_tool.backend import run_operation
from ns2_nup_tool.streaming import open_container
from ns2_nup_tool.launch import LEGACY_LAUNCH_POLICY_VALUE, LAUNCH_POLICY_TAG
from tests.fixtures import TITLE_ID, add_update_program, make_dump, make_flat_dump, make_npdm, make_program


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "dump"
        make_dump(self.source)
        self.update = self.source / "updates/458752"
        add_update_program(self.update, 7, 458752)
        (self.source / "base/exefs/rtld").write_bytes(b"base fallback")
        (self.source / "base/base-only.txt").write_bytes(b"must not remain in replacement base")
        (self.update / "romfs/update-only.bin").write_bytes(b"new update content")
        self.output = self.root / "game.nup"

    def tearDown(self):
        self.temp.cleanup()

    def call(self, operation, **options):
        return run_operation({"operation": operation, "source": str(self.source),
            "file": str(self.output), "output": str(self.output), **options}, lambda: None, lambda *args: None)

    @staticmethod
    def payload(reader, package, relative):
        node = resolve_path(reader, package, relative)
        return reader.read_file(node.index)

    def test_default_retains_original_base_program(self):
        scanned = self.call("scan")
        self.assertTrue(scanned["update_executable"]["available"])
        self.call("pack")
        with open_container(self.output) as reader:
            self.assertEqual(self.payload(reader, reader.packages[0], "exefs/main"), (self.source / "base/exefs/main").read_bytes())
        self.assertFalse(self.call("inspect")["packages"][0]["prefer_update_executable"])

    def test_enabled_replaces_both_folders_and_deduplicates_payload(self):
        before = {p.relative_to(self.source): p.read_bytes() for p in self.source.rglob("*") if p.is_file()}
        self.call("pack", prefer_update_executable=True)
        with open_container(self.output) as reader:
            base = reader.packages[0]
            update = next(p for p in reader.packages if p.kind == F.KIND_UPDATE)
            for name in ("main", "main.npdm", "sdk"):
                self.assertEqual(self.payload(reader, base, "exefs/" + name), (self.update / "exefs" / name).read_bytes())
            for removed in ("exefs/rtld", "romfs/data/raw.bin", "romfs/empty", "base-only.txt"):
                self.assertIsNone(resolve_path(reader, base, removed))
            self.assertEqual(self.payload(reader, base, "romfs/update-only.bin"), b"new update content")
            self.assertEqual(app_meta(reader, base)[F.TLV_BUILD_ID], bytes([7]) * 32)
            self.assertEqual(app_meta(reader, base)[F.TLV_NPDM], (self.update / "exefs/main.npdm").read_bytes())
            main = resolve_path(reader, base, "exefs/main")
            patch_main = resolve_path(reader, update, "exefs/main")
            self.assertEqual(reader.files[main.index][3:6], reader.files[patch_main.index][3:6])
            base_romfs = resolve_path(reader, base, "romfs/update-only.bin")
            update_romfs = resolve_path(reader, update, "romfs/update-only.bin")
            self.assertEqual(reader.files[base_romfs.index][3:6], reader.files[update_romfs.index][3:6])
            self.assertEqual(self.payload(reader, next(p for p in reader.packages if p.kind == F.KIND_ADDON),
                                          "romfs/addon.bin"), b"synthetic add-on" * 100)
        extracted = self.root / "base-content"
        self.call("extract", package=0, output=str(extracted))
        self.assertEqual({p.relative_to(extracted): p.read_bytes() for p in extracted.rglob("*") if p.is_file()},
                         {p.relative_to(self.update): p.read_bytes() for p in self.update.rglob("*") if p.is_file()})
        self.assertTrue(verify(str(self.output), deep=True)[0])
        self.assertTrue(self.call("inspect")["packages"][0]["prefer_update_executable"])
        self.assertTrue(self.call("inspect")["packages"][0]["replace_base_content"])
        self.assertEqual({p.relative_to(self.source): p.read_bytes() for p in self.source.rglob("*") if p.is_file()}, before)

    def test_latest_main_wins_without_retaining_missing_romfs_or_npdm(self):
        latest = self.source / "updates/524288/exefs"
        latest.mkdir(parents=True)
        (latest / "main").write_bytes(make_program(8))
        self.assertEqual(self.call("scan")["update_executable"]["version"], 524288)
        self.call("pack", prefer_update_executable=True)
        with open_container(self.output) as reader:
            base = reader.packages[0]
            self.assertEqual(self.payload(reader, base, "exefs/main"), make_program(8))
            self.assertEqual(app_meta(reader, base)[F.TLV_BUILD_ID], bytes([8]) * 32)
            self.assertNotIn(F.TLV_NPDM, app_meta(reader, base))
            self.assertIsNone(resolve_path(reader, base, "exefs/main.npdm"))
            self.assertIsNone(resolve_path(reader, base, "romfs"))
        self.assertTrue(verify(str(self.output), deep=True)[0])

    def test_flat_v0_layout_repair_and_executable_preference_work_together(self):
        flat = self.root / "flat"
        make_flat_dump(flat)
        add_update_program(flat / "updates", 9, 0)
        self.call("pack", source=str(flat), prefer_update_executable=True)
        self.assertTrue((flat / "updates/0/exefs/main").is_file())
        with open_container(self.output) as reader:
            self.assertEqual(self.payload(reader, reader.packages[0], "exefs/main"), make_program(9))
        self.assertTrue(verify(str(self.output), deep=True)[0])

    def test_mismatched_or_missing_main_is_rejected_before_output(self):
        (self.update / "exefs/main.npdm").write_bytes(make_npdm(458752, TITLE_ID + 1))
        self.assertFalse(self.call("scan")["update_executable"]["available"])
        with self.assertRaisesRegex(ValueError, "title ID"):
            self.call("pack", prefer_update_executable=True)
        (self.update / "exefs/main").unlink()
        with self.assertRaisesRegex(ValueError, "No update main"):
            self.call("pack", prefer_update_executable=True)
        self.assertFalse(self.output.exists())

    def test_later_update_refreshes_preferred_base_view(self):
        self.call("pack", prefer_update_executable=True)
        original = self.output.read_bytes()
        new_update = self.root / "524288"
        add_update_program(new_update, 8, 524288)
        (new_update / "romfs").mkdir()
        (new_update / "romfs/latest.bin").write_bytes(b"latest RomFS")
        result = self.root / "updated.nup"
        self.call("add_updates", update_source=str(new_update), output=str(result))
        with open_container(result) as reader:
            base = reader.packages[0]
            self.assertEqual(self.payload(reader, base, "exefs/main"), make_program(8))
            self.assertEqual(self.payload(reader, base, "exefs/sdk"), b"matching sdk\x08")
            self.assertEqual(self.payload(reader, base, "romfs/latest.bin"), b"latest RomFS")
            self.assertIsNone(resolve_path(reader, base, "romfs/update-only.bin"))
            self.assertEqual(app_meta(reader, base)[F.TLV_BUILD_ID], bytes([8]) * 32)
            self.assertEqual(app_meta(reader, base)[F.TLV_NPDM], make_npdm(524288))
            self.assertEqual([p.version for p in reader.packages if p.kind == F.KIND_UPDATE], [524288])
        self.assertTrue(verify(str(result), deep=True)[0])
        self.assertEqual(self.output.read_bytes(), original)

    def test_later_update_without_main_keeps_replacement_base(self):
        self.call("pack", prefer_update_executable=True)
        incoming = self.root / "524288"
        (incoming / "romfs").mkdir(parents=True)
        (incoming / "romfs/new.bin").write_bytes(b"RomFS-only update")
        result = self.root / "updated.nup"
        self.call("add_updates", update_source=str(incoming), output=str(result), confirm_identity=True)
        with open_container(result) as reader:
            base = reader.packages[0]
            self.assertEqual(self.payload(reader, base, "exefs/main"), make_program(7))
            self.assertEqual(self.payload(reader, base, "romfs/update-only.bin"), b"new update content")
            self.assertIsNone(resolve_path(reader, base, "romfs/new.bin"))
        self.assertTrue(verify(str(result), deep=True)[0])

    def test_legacy_policy_remains_exefs_only_when_adding_updates(self):
        def legacy_marker(block):
            metadata = M.parse_block(block)
            metadata[LAUNCH_POLICY_TAG] = LEGACY_LAUNCH_POLICY_VALUE
            return M.serialize_block(metadata)

        with patch("ns2_nup_tool.streaming.mark_launch_policy", side_effect=legacy_marker):
            self.call("pack", prefer_update_executable=True)
        info = self.call("inspect")["packages"][0]
        self.assertTrue(info["prefer_update_executable"])
        self.assertFalse(info["replace_base_content"])
        incoming = self.root / "524288"
        add_update_program(incoming, 8, 524288)
        (incoming / "exefs/sdk").unlink()
        result = self.root / "legacy-updated.nup"
        self.call("add_updates", update_source=str(incoming), output=str(result))
        with open_container(result) as reader:
            base = reader.packages[0]
            self.assertEqual(self.payload(reader, base, "exefs/main"), make_program(8))
            self.assertEqual(self.payload(reader, base, "exefs/sdk"), b"matching sdk\x07")
            self.assertEqual(self.payload(reader, base, "romfs/update-only.bin"), b"new update content")
        self.assertTrue(verify(str(result), deep=True)[0])
