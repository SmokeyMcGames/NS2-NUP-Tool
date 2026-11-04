"""Fetch pinned corresponding sources and collect their license/notice texts."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parent.parent


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def fetch(item):
    cache = ROOT / "build/dependency-sources"
    cache.mkdir(parents=True, exist_ok=True)
    if (Path(item["name"]).name != item["name"] or not item["url"].startswith("https://")
            or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])):
        raise ValueError("Invalid corresponding-source manifest entry")
    target = cache / item["name"]
    if not target.is_file() or digest(target) != item["sha256"]:
        temporary = target.with_suffix(target.suffix + ".part")
        with urllib.request.urlopen(item["url"], timeout=90) as response, temporary.open("wb") as output:
            if not response.url.startswith("https://"):
                raise ValueError("Source download redirected to an insecure URL")
            shutil.copyfileobj(response, output, 4 * 1024 * 1024)
        if digest(temporary) != item["sha256"]:
            raise ValueError(f"Source archive hash mismatch: {item['name']}")
        temporary.replace(target)
    return target


def collect_notices(archive):
    output = ROOT / "licenses/dependencies" / archive.name.split(".tar.")[0]
    output.mkdir(parents=True, exist_ok=True)
    count = 0
    with tarfile.open(archive, "r|*") as source:
        for member in source:
            path = PurePosixPath(member.name)
            name = path.name.lower()
            if not (any(part.lower() == "licenses" for part in path.parts)
                    or name.startswith(("license", "licence", "copying", "copyright", "notice"))
                    or name == "qt_attribution.json"):
                continue
            if path.suffix.lower() in (".py", ".cpp", ".c", ".h", ".js", ".qml"):
                continue
            if not member.isfile() or member.size > 2 * 1024 * 1024:
                continue
            if path.is_absolute() or any(part in ("..", ".") or ":" in part or "\\" in part for part in path.parts):
                raise ValueError("Unsafe archive notice path")
            data = source.extractfile(member).read()
            if b"\0" in data:
                continue
            destination = output.joinpath(*path.parts[1:])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            count += 1
    return count


def main():
    manifest = json.loads((ROOT / "distribution/sources.json").read_text())
    with ThreadPoolExecutor(max_workers=4) as pool:
        archives = list(pool.map(fetch, manifest))
    for archive in archives:
        print(f"{archive.name}: verified; {collect_notices(archive)} notice files", flush=True)
    runtime_notice = Path(sys.base_prefix) / "LICENSE.txt"
    if not runtime_notice.is_file():
        raise ValueError("The Windows Python runtime license is missing")
    runtime_dir = ROOT / "licenses/dependencies/windows-runtime"
    runtime_dir.mkdir(exist_ok=True)
    shutil.copyfile(runtime_notice, runtime_dir / "PYTHON-RUNTIME-LICENSE.txt")


if __name__ == "__main__":
    main()
