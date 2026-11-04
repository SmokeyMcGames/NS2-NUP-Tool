"""Exercise the shipped executable's worker mode, without an external Python runtime."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from tests.fixtures import PNG, make_dump, make_flat_dump
from tests.fixtures import add_update_program, make_program


def main():
    executable = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else root / "dist/NS2 NUP Tool/NS2 NUP Tool.exe"
    results = []
    with tempfile.TemporaryDirectory(prefix="nup-portable-check-") as temporary:
        work = Path(temporary)
        source = work / "Synthetic dump"
        make_dump(source)
        output = work / "game.nup"
        icon = work / "icon.png"
        icon.write_bytes(PNG)

        def invoke(operation, expected_status="ok", cancelled=False, **options):
            job = work / f"job-{len(results)}"
            job.mkdir()
            request = {"operation": operation, "source": str(source), "file": str(output),
                       "output": str(output), **options}
            (job / "request.json").write_text(json.dumps(request), encoding="utf-8")
            if cancelled:
                (job / "cancel").touch()
            process = subprocess.run([str(executable), "--worker", str(job)], timeout=60,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            response = json.loads((job / "result.json").read_text(encoding="utf-8"))
            if response["status"] != expected_status or (process.returncode != 0) != (expected_status != "ok"):
                raise RuntimeError(response)
            results.append({"operation": operation, "expected_status": expected_status, "status": "passed"})
            return response.get("result", response)

        assert len(invoke("scan")["packages"]) == 3
        assert invoke("pack", name="Portable test", publisher="Test publisher", display_version="1.2.3",
                      icon=str(icon), lang_names={"ja": "テスト"}, lang_icons={"ja": str(icon)})["verification"]["ok"]
        original = invoke("inspect")
        assert not any(row[0] == ".listing" for row in original["files"])
        assert original["packages"][0]["name"] == "Portable test"
        assert original["packages"][0]["lang_names"] == {"ja": "テスト"}
        assert original["packages"][0]["lang_icons"] == ["ja"]
        assert original["packages"][0]["icon_size"] == len(PNG)
        assert invoke("verify", deep=True)["ok"]
        assert invoke("verify", deep=False)["ok"]
        invoke("edit", inplace=True, package=2, name="DLC test")
        assert invoke("inspect")["packages"][2]["name"] == "DLC test"
        invoke("extract", package=2, output=str(work / "addon"))
        assert (work / "addon/romfs/addon.bin").exists()
        invoke("extract", package=0, subtree="romfs/data", output=str(work / "subtree"))
        assert (work / "subtree/raw.bin").read_bytes() == (source / "base/romfs/data/raw.bin").read_bytes()
        copy = work / "edited.nup"
        invoke("edit", package=0, output=str(copy), clear_icon=True, clear_display_version=True,
               clear_publisher=True, lang_names={"ja": ""}, lang_icons={"ja": ""})
        edited = invoke("inspect", file=str(copy))
        assert edited["packages"][0]["publisher"] == edited["packages"][0]["display_version"] == ""
        assert edited["packages"][0]["lang_names"] == {} and edited["packages"][0]["lang_icons"] == []
        assert edited["packages"][0]["icon_size"] == 0 and edited["files"] == original["files"]
        invoke("pack", expected_status="error")
        invoke("extract", expected_status="error", package=2, output=str(work / "addon"))
        cancelled_output = work / "cancelled.nup"
        invoke("pack", expected_status="cancelled", cancelled=True, output=str(cancelled_output))
        assert not cancelled_output.exists()
        listing_output = work / "listings.nup"
        invoke("pack", keep_listings=True, level=-5, output=str(listing_output))
        assert any(row[0] == ".listing" for row in invoke("inspect", file=str(listing_output))["files"])
        incoming = work / "524288"
        (incoming / "romfs").mkdir(parents=True)
        (incoming / "romfs/new.bin").write_bytes(b"Portable update test" * 100)
        (incoming / "romfs/.listing").write_bytes(b"dump-tool listing")
        updated = work / "updated.nup"
        assert invoke("preview_updates", update_source=str(incoming))["requires_confirmation"]
        invoke("add_updates", expected_status="error", update_source=str(incoming), output=str(updated))
        assert not updated.exists()
        assert invoke("add_updates", update_source=str(incoming), output=str(updated),
                      confirm_identity=True)["verification"]["ok"]
        updated_info = invoke("inspect", file=str(updated))
        assert not any(row[0] == ".listing" for row in updated_info["files"])
        assert len(updated_info["packages"]) == 3
        assert [p["version"] for p in updated_info["packages"] if p["kind"] == "update"] == [524288]
        assert updated_info["packages"][0]["display_version"] == "V524288"
        assert updated_info["packages"][2]["display_version"] == "V524288"
        assert invoke("verify", file=str(updated), deep=True)["ok"]
        invoke("extract", file=str(updated), package=2, output=str(work / "new-update"))
        assert (work / "new-update/romfs/new.bin").read_bytes() == (incoming / "romfs/new.bin").read_bytes()
        invoke("preview_updates", expected_status="error", file=str(updated), update_source=str(incoming))
        direct = work / "direct-layout"
        make_flat_dump(direct)
        direct_output = work / "direct-layout.nup"
        direct_scan = invoke("scan", source=str(direct))
        assert [p["kind"] for p in direct_scan["packages"]] == ["base", "update"]
        assert direct_scan["version_defaulted"]
        assert "V0" in " ".join(direct_scan["warnings"])
        invoke("pack", source=str(direct), output=str(direct_output), update_version="0")
        assert (direct / "updates/0/romfs/update.bin").is_file()
        assert not (direct / "updates/romfs").exists()
        direct_info = invoke("inspect", file=str(direct_output))
        assert len(direct_info["packages"]) == 2 and direct_info["packages"][1]["version"] == 0
        assert direct_info["packages"][0]["display_version"] == "V0"
        assert invoke("verify", file=str(direct_output), deep=True)["ok"]
        add_update_program(source / "updates/458752", 7, 458752)
        assert invoke("scan")["update_executable"]["available"]
        preferred = work / "preferred.nup"
        invoke("pack", output=str(preferred), prefer_update_executable=True)
        preferred_info = invoke("inspect", file=str(preferred))
        assert preferred_info["packages"][0]["prefer_update_executable"]
        assert preferred_info["packages"][0]["replace_base_content"]
        assert preferred_info["packages"][0]["build_id"] == (bytes([7]) * 32).hex().upper()
        invoke("extract", file=str(preferred), package=0, output=str(work / "preferred-base"))
        assert (work / "preferred-base/exefs/main").read_bytes() == make_program(7)
        assert not (work / "preferred-base/romfs/data/raw.bin").exists()
        assert {p.relative_to(work / "preferred-base"): p.read_bytes()
                for p in (work / "preferred-base").rglob("*") if p.is_file()} == {
                p.relative_to(source / "updates/458752"): p.read_bytes()
                for p in (source / "updates/458752").rglob("*") if p.is_file()}
        assert invoke("verify", file=str(preferred), deep=True)["ok"]
        complete = work / "complete-dump"
        extracted = invoke("extract", scope="all", output=str(complete))
        assert extracted["packages"] == 3
        assert not (complete / "base/romfs/.listing").exists()
        assert (complete / "updates/458752/romfs/data/repeated.bin").exists()
        assert (complete / "dlc/040074A01BF13001/0/romfs/addon.bin").exists()
        assert invoke("scan", source=str(complete))["files"] == extracted["files"]
        repacked = work / "repacked.nup"
        invoke("pack", source=str(complete), output=str(repacked))
        info = invoke("inspect", file=str(repacked))
        assert [p["kind"] for p in info["packages"]] == ["base", "update", "addon"]
        assert info["packages"][0]["icon"] == original["packages"][0]["icon"]
        assert info["packages"][2]["name"] == "DLC test"
        assert info["files"] == original["files"]
        assert invoke("verify", file=str(repacked), deep=True)["ok"]
    report = {"executable": str(executable), "checks": results}
    (root / "build/portable-smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Portable executable: {len(results)} checks passed.")


if __name__ == "__main__":
    main()
