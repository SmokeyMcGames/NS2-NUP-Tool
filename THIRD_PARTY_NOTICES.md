# Third-party components and attribution

The GPL-3.0-only license covers original NS2 NUP Tool files, including nup_core.
Dependencies retain their own licenses; attribution does not change those terms.

| Component | Version / source | License information |
| --- | --- | --- |
| Qt | 6.12.0, [Qt Project](https://www.qt.io/) | LGPL/GPL alternatives and individual third-party licenses; full Qt source and notices accompany releases |
| PySide6 Essentials / shiboken6 | 6.12.0, [Qt for Python](https://doc.qt.io/qtforpython-6/) | LGPL-3.0-only / GPL-2.0-only / GPL-3.0-only alternatives; matching pyside-setup sources included |
| python-zstandard | 0.25.0, [upstream](https://github.com/indygreg/python-zstandard) | BSD-3-Clause; source includes the bundled Zstandard implementation and its notices |
| CPython | 3.12.10, [Python](https://www.python.org/) | PSF license and bundled component notices; matching source archive included |
| PyInstaller bootloader | 6.22.3, [license](https://pyinstaller.org/en/stable/license.html) | GPL with distribution exception for generated bundles; certain files Apache-2.0; source included |
| Microsoft C/C++ runtime | From the official Windows Python/Qt distributions | Microsoft distributable runtime terms, not GPL; notices are retained in the Windows Python runtime license |

## NUP format recognition

Credit for the NUP format and reference implementation belongs to
**[a55uka and contributors](https://github.com/a55uka/nup)**. Our original backend
implements the published v1 format; it does not bundle or relicense their code.

The optional development oracle uses revision
744fb7e30ce3ace787f1839ee3e7f8a010e36c04 in an ignored checkout. That revision has
no declared license. It is not a production dependency, and the release checks
reject its Python package, metadata directory, or reference documentation.
See [implementation provenance](docs/FORMAT_IMPLEMENTATION.md).

## Notices and corresponding source

Portable builds contain full dependency notice/license texts under
_internal/licenses/dependencies. These are collected from SHA-256-pinned official
source archives, alongside the Windows Python runtime's own license file. The
source archives are published as assets on the same release as the app. The
distribution manifest records their exact versions, URLs, and hashes.

Qt/PySide DLLs remain separate and replaceable. You may modify the application
and replace/rebuild those components according to their licenses. No project
term limits reverse engineering or relinking where permitted by those licenses.
Build instructions and source-access directions are in [Releasing](docs/RELEASING.md).
The optional software OpenGL fallback DLL and unused PDF/virtual-keyboard/QML
components are excluded from the portable app; the UI uses Qt's raster painter.

Microsoft distributable runtime code is subject to the applicable Microsoft
terms described in the included Python Windows runtime license. Preserve its
notices; do not imply Microsoft endorsement, distribute it for non-Microsoft
platforms, or include it in malicious/deceptive/unlawful programs. These conditions
apply to the Microsoft components, not to the original GPL project code.

## Assets and data

Pixel sprites, lettering, app icon, banner, and dashboard preview are generated
from original project code. No Nintendo game content, keys, firmware, Nintendo
logos, fonts, or downloaded storefront artwork are distributed. Tests generate
synthetic content. Artwork retrieved at runtime retains its rights holders' terms
and is not licensed by this repository.

Nintendo and related product names identify compatibility and remain their
owners' trademarks. This project is independent of Nintendo and the NUP author.
Software licensing does not grant rights to game data or circumvent applicable law.
