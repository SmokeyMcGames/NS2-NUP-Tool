# Building and releasing

## What a release contains

- A Windows x64 portable ZIP containing the app, original nup_core backend,
  separate Qt DLLs, project license, guide, and full dependency notices.
- A ZIP of the exact project source commit.
- Matching Qt, PySide6/shiboken6, Python, python-zstandard/Zstandard, and PyInstaller
  source archives.
- BUILD-MANIFEST.json with dependency versions, bundled modules, file hashes,
  and corresponding-source provenance.
- SHA256SUMS.txt for the downloadable assets.

The unlicensed upstream NUP implementation is never bundled. The release script
inspects the executable's embedded module archive and rejects upstream nup
modules, reference documentation, or upstream package metadata.

## Maintainer workflow

1. Update the app version in ns2_nup_tool/__init__.py and CHANGELOG.md. Review any
   dependency changes and update distribution/sources.json to matching official
   sources and SHA-256 digests. Keep Python pinned to 3.12.10 for this release line.
2. Run Setup.ps1 -ReferenceTests, enable NUP_REFERENCE_TESTS=1, and run Build.ps1.
   Review UI changes and test data handling with synthetic input.
3. Before packaging, run tools/prepare_dependencies.py with the project's Python.
   It downloads and verifies corresponding sources and collects license notices.
   Run Build.ps1 again if those materials changed after the previous build.
4. Commit the reviewed files to main, then push an annotated vX.Y.Z tag matching
   the source version. The release workflow checks dependencies, builds, tests,
   packages the app and source assets, then publishes through a draft release.

Only the release publish job receives contents-write permission. Pull-request
builds have read-only tokens. Actions are pinned to commit SHAs. CI artifacts
contain test reports; published binaries come from the version-tag build.

The workflow creates a draft and uploads all assets before making it public.
If publishing is interrupted, inspect the draft and run before retrying. Do not
replace release assets silently. Publish a new version for corrected binaries.

## Rebuild and replace libraries

Extract the entire portable folder, including _internal. The GUI does not impose
code-signing checks on replacement Qt/PySide libraries. Compatible replacement
DLLs can be placed in the same _internal locations, with their required plugins.
Alternatively, rebuild the whole application from its source and modified
dependencies using the same Python architecture and ABI.

Qt sources include their build configuration and instructions. PySide/shiboken
sources include their build tooling; see the official [Qt for Python build
instructions](https://doc.qt.io/qtforpython-6/building_from_source/index.html).
The project does not patch these dependencies. Corresponding source archives
are hosted beside the application asset, not merely linked to a moving branch.
Microsoft Windows runtime components are system/runtime redistributables and
remain under their own terms; see the included Windows Python runtime license.

## Validation and limits

Build.ps1 runs the full test suite, packaged Qt startup/navigation/shutdown,
and packaged conversion checks. The release script requires successful reports,
exact dependency versions, verified source archives, and collected license files.
It does not certify game/emulator compatibility or legal compliance in every
jurisdiction. Releases are unsigned unless a separate signing process is established.

References: [GNU GPLv3](https://www.gnu.org/licenses/gpl-3.0.html),
[Qt GPL/LGPL obligations](https://www.qt.io/development/open-source-lgpl-obligations),
and [PyInstaller's distribution exception](https://pyinstaller.org/en/stable/license.html).
