# NS2 NUP Tool 0.3.0

The first public release includes an original GPLv3 implementation of the NUP v1
format. The upstream reference implementation is used only in development
compatibility tests and is not included in the app.

## Download and run

Download **NS2-NUP-Tool-v0.3.0-windows-x64.zip**, extract the entire folder, and run
**NS2 NUP Tool.exe**. Keep `_internal` beside the executable. Python does not need
to be installed separately. This Windows x64 build is unsigned.

## Included workflows

- Create NUPs from decrypted base/update/DLC folders, with automatic metadata discovery and optional Nintendo US lookup.
- Extract the whole NUP by default, or select one package/subtree. Keep `.ns2-nup` metadata for complete repacking.
- Replace older updates in a newly saved NUP while preserving the original file.
- Optionally use an update's complete ExeFS/RomFS as the base when it has its own main executable.
- Inspect file trees, edit metadata and artwork, verify hashes, and stream large operations with cancellation.
- Classic Red pixel dashboard, animated backgrounds/transitions, responsive layouts, and Reduce motion.

`.listing` files are ignored by default when packing. Unknown update versions use
V0 with a warning. The app does not decrypt files or include game content, keys,
firmware, or an emulator. Successful container validation does not guarantee gameplay.

## Validation and source

The Windows release workflow runs the full automated suite, including malformed
containers and bidirectional reference interoperability, then checks packaged GUI
startup/navigation/shutdown and 37 packaged operations before publication.

`SHA256SUMS.txt` lists asset hashes. `BUILD-MANIFEST.json` records the runtime,
dependencies, module inventory, and file hashes. The project-source ZIP and matching
Qt, PySide/shiboken, Python, python-zstandard/Zstandard, and PyInstaller source
archives accompany this release. Full dependency notices are inside the app.

NUP format credit: [a55uka/nup](https://github.com/a55uka/nup). Our GPLv3 license
covers the original app and backend; third-party components retain their own terms.
This project is independent of Nintendo and the upstream author.
