"""Update addition must preserve old bytes and publish only verified copies."""

import hashlib
import shutil
import struct
import tempfile
import unittest
from pathlib import Path

from nup_core import format as F
from nup_core.access import app_meta, extract_tree
from nup_core.verify import verify as core_verify

from ns2_nup_tool.backend import Cancelled, run_operation
from ns2_nup_tool.streaming import open_container
from tests.fixtures import PNG, TITLE_ID, make_dump


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.dump = self.root / "dump"
        make_dump(self.dump)
        self.original = self.root / "original.nup"
        self.updated = self.root / "updated.nup"
        self.icon = self.root / "icon.png"
        self.icon.write_bytes(PNG)
        self.call("pack", source=str(self.dump), output=str(self.original), name="Keep this title",
                  publisher="Keep publisher", icon=str(self.icon), lang_names={"ja": "テスト"})
        self.old_bytes = self.original.read_bytes()
        self.update = self.root / "524288"
        (self.update / "exefs").mkdir(parents=True)
        (self.update / "romfs").mkdir()
        (self.update / "exefs/main.npdm").write_bytes(b"ACI0" + bytes(12) + struct.pack("<Q", TITLE_ID))
        (self.update / "romfs/new.bin").write_bytes(b"New update content" * 3000)
        (self.update / "romfs/empty").touch()

    def tearDown(self):
        self.temp.cleanup()

    def call(self, operation, **options):
        return run_operation({"operation": operation, "file": str(self.original),
            "output": str(self.updated), "update_source": str(getattr(self, "update", "")),
            **options}, lambda: None, lambda *args: None)

    def test_replacement_preserves_base_dlc_metadata_and_original(self):
        (self.update / "romfs/.listing").write_bytes(b"dump-tool listing")
        plan = self.call("preview_updates")
        self.assertFalse(plan["requires_confirmation"])
        self.assertEqual(plan["current_version"], 458752)
        result = self.call("add_updates")
        self.assertTrue(result["verification"]["ok"])
        self.assertEqual(self.original.read_bytes(), self.old_bytes)
        self.assertTrue(core_verify(str(self.updated), deep=True)[0])
        with open_container(self.original) as before, open_container(self.updated) as after:
            self.assertEqual(len(after.packages), 3)
            self.assertEqual(after.packages[-1].version, 524288)
            self.assertEqual(after.packages[-1].flags, 0)
            self.assertNotEqual(before.super["uuid"], after.super["uuid"])
            retained = [p for p in before.packages if p.kind != F.KIND_UPDATE]
            for old, new in zip(retained, after.packages):
                expected_meta = app_meta(before, old)
                if old.kind == F.KIND_BASE:
                    expected_meta[F.TLV_DISPLAY_VERSION] = b"V524288"
                self.assertEqual(expected_meta, app_meta(after, new))
                self.assertEqual((old.kind, old.title_id, old.version), (new.kind, new.title_id, new.version))
                self.assertEqual(self.package_payloads(before, old), self.package_payloads(after, new))
            self.assertNotIn(458752, [p.version for p in after.packages])
            self.assertEqual(app_meta(after, after.packages[-1])[F.TLV_DISPLAY_VERSION], b"V524288")
            extract_tree(after, str(self.root / "extract"), after.packages[-1].root_dir)
        self.assertEqual((self.root / "extract/romfs/new.bin").read_bytes(), (self.update / "romfs/new.bin").read_bytes())
        self.assertFalse((self.root / "extract/romfs/.listing").exists())

    def test_update_only_nup_and_multiple_versions(self):
        bundle = self.root / "new updates"
        shutil.copytree(self.update, bundle / "updates/524288")
        shutil.copytree(self.update, bundle / "updates/589824")
        incoming = self.root / "incoming.nup"
        self.call("pack", source=str(bundle), output=str(incoming))
        self.call("add_updates", update_source=str(incoming))
        with open_container(self.updated) as reader:
            self.assertEqual([p.version for p in reader.packages if p.kind == F.KIND_UPDATE], [589824])
            self.assertEqual(reader.packages[-1].flags, 0)

    @staticmethod
    def package_payloads(reader, package):
        result, pending = {}, [(package.root_dir, "")]
        while pending:
            directory, path = pending.pop()
            _, first, count = reader.dirs[directory]
            for child in reader.children[first:first+count]:
                if child < reader.dir_count:
                    pending.append((child, path + reader.dirs[child][0].decode() + "/"))
                else:
                    file = reader.files[child-reader.dir_count]
                    result[path+file[0].decode()] = (file[1:3], file[4:], bytes(reader._mm[file[3]:file[3]+file[4]]))
        return result

    def test_unknown_identity_requires_confirmation(self):
        (self.update / "exefs/main.npdm").unlink()
        self.assertTrue(self.call("preview_updates")["requires_confirmation"])
        with self.assertRaisesRegex(ValueError, "Confirm"):
            self.call("add_updates")
        self.assertFalse(self.updated.exists())
        self.call("add_updates", confirm_identity=True)
        with open_container(self.updated) as reader:
            self.assertEqual(reader.packages[-1].title_id, TITLE_ID)

    def test_rejects_mismatch_and_old_or_invalid_versions(self):
        for version in ("-1", "458752", "1.2.3", str(2**32)):
            with self.subTest(version=version), self.assertRaises(ValueError):
                self.call("add_updates", update_version=version)
        (self.update / "exefs/main.npdm").write_bytes(b"ACI0" + bytes(12) + struct.pack("<Q", TITLE_ID+1))
        with self.assertRaisesRegex(ValueError, "Different game"):
            self.call("add_updates", confirm_identity=True)
        self.assertEqual(self.original.read_bytes(), self.old_bytes)
        self.assertFalse(self.updated.exists())

    def test_rejects_mixed_bundle_and_existing_or_nested_output(self):
        with self.assertRaisesRegex(ValueError, "only update"):
            self.call("add_updates", update_source=str(self.dump))
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.call("add_updates", output=str(self.original))
        with self.assertRaisesRegex(ValueError, "outside"):
            self.call("add_updates", output=str(self.update / "bad.nup"))

    def test_cancellation_during_copy_cleans_output_and_keeps_original(self):
        copying = False
        def report(done, total, message):
            nonlocal copying
            copying |= message.startswith("Copying stored content")
        def check():
            if copying:
                raise Cancelled()
        with self.assertRaises(Cancelled):
            run_operation({"operation":"add_updates", "file":str(self.original),
                "update_source":str(self.update), "output":str(self.updated)}, check, report)
        self.assertEqual(self.original.read_bytes(), self.old_bytes)
        self.assertFalse(self.updated.exists())
        self.assertFalse(list(self.root.glob(".nup-update-*")))

    def test_corrupt_original_never_publishes_updated_container(self):
        with open_container(self.original) as reader:
            entry = next(f for f in reader.files if f[5] == F.CODEC_RAW and f[1] > 0)
        with self.original.open("r+b") as file:
            file.seek(entry[3]); file.write(b"broken")
        corrupted = self.original.read_bytes()
        with self.assertRaisesRegex(ValueError, "failed verification"):
            self.call("add_updates")
        self.assertEqual(self.original.read_bytes(), corrupted)
        self.assertFalse(self.updated.exists())

    def test_second_add_rejects_duplicate_version(self):
        self.call("add_updates")
        with self.assertRaisesRegex(ValueError, "already present"):
            self.call("preview_updates", file=str(self.updated))

    def test_unnumbered_update_uses_v0_warning_and_replaces_previous_update(self):
        unknown = self.root / "new update"
        (unknown / "romfs").mkdir(parents=True)
        (unknown / "romfs/content.bin").write_bytes(b"Update content")
        plan = self.call("preview_updates", update_source=str(unknown))
        self.assertTrue(plan["version_defaulted"])
        self.assertEqual(plan["updates"][0]["version"], 0)
        self.assertIn("Update order cannot be verified", " ".join(plan["warnings"]))
        self.call("add_updates", update_source=str(unknown), update_version="0", confirm_identity=True)
        info = self.call("inspect", file=str(self.updated))
        self.assertEqual([p["version"] for p in info["packages"] if p["kind"] == "update"], [0])
        self.assertEqual(info["packages"][0]["display_version"], "V0")
        self.assertTrue(core_verify(str(self.updated), deep=True)[0])
        self.assertEqual(self.original.read_bytes(), self.old_bytes)

    def test_invalid_nup_does_not_leave_a_windows_file_lock(self):
        broken = self.root / "broken.nup"
        broken.write_bytes(b"invalid container")
        with self.assertRaises(F.NupError) as caught:
            self.call("preview_updates", update_source=str(broken))
        self.assertIsNotNone(caught.exception)
        broken.rename(self.root / "unlocked.nup")
