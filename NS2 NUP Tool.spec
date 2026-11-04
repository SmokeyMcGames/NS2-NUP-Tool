# PyInstaller recipe: dynamic Qt libraries remain separate in the portable folder.
from pathlib import Path
import os
import sys
from PyInstaller.utils.hooks import copy_metadata

root = Path(SPECPATH)
# Do not collect unrelated DLLs from developer tools on PATH. Qt expects the
# Windows ICU ABI; Poppler's identically named ICU DLL exports a different ABI.
windows = Path(os.environ.get("SystemRoot", "C:/Windows"))
os.environ["PATH"] = os.pathsep.join([
    str(Path(sys.executable).parent), sys.base_prefix,
    str(windows / "System32"), str(windows),
])
datas = [(str(root / "README.md"), "."),
         (str(root / "THIRD_PARTY_NOTICES.md"), "."),
         (str(root / "LICENSE"), "."), (str(root / "NOTICE"), "."),
         (str(root / "licenses"), "licenses")]
for distribution in ("PySide6_Essentials", "shiboken6", "zstandard"):
    datas += copy_metadata(distribution)

a = Analysis([str(root / "main.py")], pathex=[str(root)], binaries=[], datas=datas,
             hiddenimports=["ns2_nup_tool.worker", "zstandard.backend_c"],
             hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=["nup", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml"],
             noarchive=False)
# Widgets use the raster painter. Omit unused PDF/virtual-keyboard plugins and
# their QML/Quick libraries, plus the optional third-party software OpenGL DLL.
unused_qt = ("qt6pdf", "qt6qml", "qt6quick", "qt6virtualkeyboard")
a.binaries = [entry for entry in a.binaries
              if not Path(entry[0]).name.lower().startswith(unused_qt)
              and Path(entry[0]).name.lower() not in {"qpdf.dll", "qtvirtualkeyboardplugin.dll", "opengl32sw.dll"}]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="NS2 NUP Tool", debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          icon=str(root / "assets/ns2-nup-tool.ico"))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="NS2 NUP Tool")
