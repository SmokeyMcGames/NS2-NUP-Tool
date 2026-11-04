"""Optional reference-oracle tests; reference code is never a runtime dependency."""

import os
from pathlib import Path
import sys
import tempfile
import unittest

from ns2_nup_tool.backend import run_operation
from nup_core.access import app_meta, iter_children
from nup_core.read import NupReader
from tests.fixtures import PNG, make_dump

ENABLED = os.environ.get("NUP_REFERENCE_TESTS") == "1"
if ENABLED:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "upstream/tools/nup"))
    from nup.pack import pack as reference_pack
    from nup.read import NupReader as ReferenceReader
    from nup.verify import verify as reference_verify


def inventory(reader):
    result = []
    for package in reader.packages:
        paths, pending = {}, [(package.root_dir, "")]
        while pending:
            directory, prefix = pending.pop()
            for node in iter_children(reader, directory):
                name = prefix + node.name.decode("utf-8")
                if node.is_dir:
                    paths[name + "/"] = None
                    pending.append((node.index, name + "/"))
                else:
                    paths[name] = reader.read_file(node.index)
        result.append(((package.kind, package.title_id, package.version, package.flags),
                       paths, app_meta(reader, package)))
    return result


@unittest.skipUnless(ENABLED, "Set NUP_REFERENCE_TESTS=1 with the pinned reference checkout to run interoperability tests")
class ReferenceCompatibilityTests(unittest.TestCase):
    def test_both_readers_agree_on_both_writers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dump = root / "synthetic"
            make_dump(dump)
            (dump / "base/romfs/empty-directory").mkdir()
            icon = root / "icon.png"
            icon.write_bytes(PNG)
            for keep in (False, True):
                ours, theirs = root / f"ours-{keep}.nup", root / f"reference-{keep}.nup"
                run_operation({"operation": "pack", "source": str(dump), "output": str(ours),
                               "keep_listings": keep, "name": "Compatibility", "display_version": "V458752",
                               "icon": str(icon), "lang_names": {"ja": "テスト"}}, lambda: None, lambda *args: None)
                reference_pack(str(theirs), str(dump), keep_listings=keep,
                               names={None: "Compatibility", "ja": "テスト"}, icons={None: str(icon)},
                               display_version="V458752")
                for path in (ours, theirs):
                    self.assertTrue(reference_verify(str(path), deep=True)[0])
                    reference = ReferenceReader(str(path))
                    try:
                        with NupReader(path) as own:
                            self.assertEqual(inventory(own), inventory(reference))
                    finally:
                        reference._mm.close()
                        reference.close()
                with NupReader(ours) as first, NupReader(theirs) as second:
                    self.assertEqual(inventory(first), inventory(second))

    def test_reference_reads_new_update_and_metadata_edit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dump = root / "dump"
            make_dump(dump)
            source, output = root / "source.nup", root / "updated.nup"
            reference_pack(str(source), str(dump))
            update = root / "524288/romfs"
            update.mkdir(parents=True)
            (update / "new.bin").write_bytes(b"new synthetic update")
            run_operation({"operation": "add_updates", "file": str(source), "output": str(output),
                           "update_source": str(update.parent), "confirm_identity": True}, lambda: None, lambda *args: None)
            run_operation({"operation": "edit", "file": str(output), "inplace": True, "name": "Edited"},
                          lambda: None, lambda *args: None)
            self.assertTrue(reference_verify(str(output), deep=True)[0])
            reference = ReferenceReader(str(output))
            try:
                with NupReader(output) as own:
                    self.assertEqual(inventory(own), inventory(reference))
            finally:
                reference._mm.close()
                reference.close()
