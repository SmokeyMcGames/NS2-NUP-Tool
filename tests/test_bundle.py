"""Full extraction and repacking must preserve every package and payload."""

import json
import tempfile
import unittest
from pathlib import Path

from nup_core import format as F
from nup_core.access import app_meta, iter_children
from nup_core.discover import PackInput

from ns2_nup_tool.backend import Cancelled, run_operation
from ns2_nup_tool.bundle import SIDECAR
from ns2_nup_tool.streaming import open_container, pack_streamed
from tests.fixtures import PNG, make_dump


def container_inventory(path):
    with open_container(path) as reader:
        result = []
        for package in reader.packages:
            files, directories = {}, []
            pending = [(package.root_dir, "")]
            while pending:
                directory, prefix = pending.pop()
                for child in iter_children(reader, directory):
                    name = prefix + child.name.decode("utf-8")
                    if child.is_dir:
                        directories.append(name)
                        pending.append((child.index, name + "/"))
                    else:
                        row = reader.files[child.index]
                        files[name] = (row[1], row[2].hex())
            result.append({"identity": (package.kind, package.title_id, package.version, package.flags),
                           "files": files, "directories": sorted(directories), "metadata": app_meta(reader, package)})
        return result


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        make_dump(self.source)
        self.nup = self.root / "original.nup"

    def tearDown(self):
        self.temp.cleanup()

    def call(self, operation, **options):
        return run_operation({"operation": operation, "source": str(self.source), "file": str(self.nup),
                              "output": str(self.nup), **options}, lambda: None, lambda *args: None)

    def test_full_default_roundtrip_preserves_all_packages_metadata_and_files(self):
        icon = self.root / "icon.png"
        icon.write_bytes(PNG)
        (self.source / "base/romfs/empty-folder").mkdir()
        self.call("pack", keep_listings=True, name="Round trip", icon=str(icon), lang_names={"ja": "テスト"}, lang_icons={"ja": str(icon)})
        self.call("edit", inplace=True, package=2, name="DLC metadata")
        original = container_inventory(self.nup)
        restored = self.root / "restored"
        result = self.call("extract", output=str(restored))
        self.assertEqual((result["scope"], result["packages"], result["files"]), ("all", 3, 9))
        for path in ("base/romfs/.listing", "updates/458752/romfs/data/repeated.bin",
                     "dlc/040074A01BF13001/0/romfs/addon.bin", SIDECAR + "/manifest.json"):
            self.assertTrue((restored / path).is_file())
        scanned = self.call("scan", source=str(restored), keep_listings=True)
        self.assertEqual(scanned["files"], 9)
        self.assertEqual(scanned["metadata"]["values"]["name"], "Round trip")
        rebuilt = self.root / "rebuilt.nup"
        self.call("pack", source=str(restored), output=str(rebuilt), keep_listings=True)
        self.assertEqual(container_inventory(rebuilt), original)
        self.assertTrue(self.call("verify", file=str(rebuilt), deep=True)["ok"])

    def test_loose_dump_files_and_folders_are_included(self):
        (self.source / "readme.txt").write_bytes(b"extra file")
        (self.source / "control").mkdir()
        (self.source / "control/custom.bin").write_bytes(b"extra folder content")
        self.call("pack")
        files = container_inventory(self.nup)[0]["files"]
        self.assertIn("readme.txt", files)
        self.assertIn("control/custom.bin", files)
        self.assertNotIn("romfs/.listing", files)

    def test_listing_artifacts_do_not_block_bundle_scan_or_pack(self):
        for relative in (".listing", "base/.listing", "updates/.listing", "dlc/.listing",
                         "dlc/040074a01bf13001/.listing", "updates/458752/romfs/.listing"):
            (self.source / relative).write_bytes(b"dump-tool listing")
        (self.source / "base/romfs/level.listing").write_bytes(b"ordinary game file")
        scan = self.call("scan")
        self.assertEqual(scan["unassigned_content"], [])
        self.assertEqual(scan["files"], 9)
        self.call("pack")
        inventory = container_inventory(self.nup)
        self.assertEqual(sum(len(p["files"]) for p in inventory), scan["files"])
        self.assertIn("romfs/level.listing", inventory[0]["files"])
        self.assertFalse(any(Path(name).name == ".listing" for p in inventory for name in p["files"]))
        self.assertTrue((self.source / "updates/.listing").is_file())

    def test_new_update_after_extraction_is_discovered(self):
        self.call("pack")
        restored = self.root / "restored"
        self.call("extract", output=str(restored))
        extra = restored / "updates/524288/romfs"
        extra.mkdir(parents=True)
        (extra / "new.bin").write_bytes(b"new update")
        self.assertEqual(len(self.call("scan", source=str(restored))["packages"]), 4)
        self.call("pack", source=str(restored), output=str(self.root / "new.nup"))
        self.assertEqual(len(container_inventory(self.root / "new.nup")), 4)

    def test_empty_and_duplicate_packages_keep_identity(self):
        package_root = self.root / "empty-package"
        package_root.mkdir()
        identities = [PackInput(F.KIND_UPDATE, str(package_root), 0x1000, 0, F.PKG_FLAG_STANDALONE_UPDATE),
                      PackInput(F.KIND_UPDATE, str(package_root), 0x1000, 0, F.PKG_FLAG_STANDALONE_UPDATE),
                      PackInput(F.KIND_ADDON, str(package_root), 0x1001, 7)]
        pack_streamed(self.nup, package_root, packages=identities, check=lambda: None, report=lambda *args: None)
        restored = self.root / "restored"
        self.call("extract", output=str(restored))
        self.call("pack", source=str(restored), output=str(self.root / "rebuilt.nup"))
        original, rebuilt = container_inventory(self.nup), container_inventory(self.root / "rebuilt.nup")
        self.assertEqual([p["identity"] for p in original], [p["identity"] for p in rebuilt])
        self.assertEqual([p["files"] for p in original], [p["files"] for p in rebuilt])

    def test_missing_package_and_unsafe_manifest_are_rejected(self):
        self.call("pack")
        restored = self.root / "restored"
        self.call("extract", output=str(restored))
        manifest = restored / SIDECAR / "manifest.json"
        data = json.loads(manifest.read_text())
        for path in ("missing", "../source/base"):
            data["packages"][0]["path"] = path
            manifest.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                self.call("pack", source=str(restored), output=str(self.root / "bad.nup"))
        self.assertFalse((self.root / "bad.nup").exists())

    def test_cancelled_full_extraction_publishes_nothing(self):
        self.call("pack")
        destination = self.root / "cancelled"
        def cancel(done, total, message):
            if message.startswith("Extracted"):
                raise Cancelled()
        with self.assertRaises(Cancelled):
            run_operation({"operation": "extract", "file": str(self.nup), "output": str(destination)}, lambda: None, cancel)
        self.assertFalse(destination.exists())
        self.assertFalse(list(self.root.glob(".nup-extract-*")))

    def test_explicit_package_and_subtree_remain_available(self):
        self.call("pack")
        destination = self.root / "selected"
        result = self.call("extract", scope="package", package=2, output=str(destination))
        self.assertEqual(result["packages"], 1)
        self.assertTrue((destination / "romfs/addon.bin").is_file())
        self.assertFalse((destination / "base").exists())
