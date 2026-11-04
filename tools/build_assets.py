"""Generate the app's code-native Windows icon and version resource."""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ns2_nup_tool.app import app_icon

root = Path(__file__).resolve().parent.parent
(root / "assets").mkdir(exist_ok=True)
app = QApplication([])
if not app_icon().pixmap(64, 64).save(str(root / "assets/ns2-nup-tool.ico")):
    raise SystemExit("Could not save the Windows icon")
