"""Render the real dashboard and an original pixel banner without user settings."""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from PySide6.QtCore import QCoreApplication, QEvent, QSettings
from PySide6.QtGui import QColor, QFontDatabase, QPainter, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from ns2_nup_tool.app import MainWindow, STYLE
from ns2_nup_tool.retro import pixel_art, pixel_text


def main():
    output = root / "docs/images"
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    # The offscreen platform may not discover installed Windows fonts itself.
    fonts = Path(os.environ.get("SystemRoot", "C:/Windows")) / "Fonts"
    for filename in ("consola.ttf", "consolab.ttf", "segoeui.ttf"):
        if (fonts / filename).is_file():
            QFontDatabase.addApplicationFont(str(fonts / filename))
    app.setStyleSheet(STYLE)
    banner = QPixmap(1440, 390)
    banner.fill(QColor("#101426"))
    painter = QPainter(banner)
    for x in range(0, 1440, 32):
        painter.fillRect(x, 0, 16, 8, QColor("#ff5268"))
        painter.fillRect(x + 16, 382, 16, 8, QColor("#ff5268"))
    for index in range(48):
        x, y = (index * 113 + 37) % 1440, (index * 71 + 23) % 360 + 15
        painter.fillRect(x, y, 3, 3, QColor("#35445e"))
    pixel_text(painter, "NS2 NUP TOOL", 74, 94, 11, "#fff0ee")
    pixel_text(painter, "PACK. UPDATE. EXPLORE.", 78, 220, 4, "#ff7183")
    pixel_text(painter, "A RETRO DESKTOP FOR NUP", 78, 280, 3, "#b8c8df")
    painter.drawPixmap(1130, 84, 220, 220, pixel_art(0))
    painter.end()
    if not banner.save(str(output / "banner.png")):
        raise RuntimeError("Could not save the banner")
    with tempfile.TemporaryDirectory() as temporary:
        settings = QSettings(str(Path(temporary) / "preview.ini"), QSettings.Format.IniFormat)
        settings.setValue("auto_store_lookup", False)
        settings.setValue("reduced_motion", True)
        window = MainWindow(settings)
        window.resize(1440, 1040)
        window.show()
        window.show_home()
        QTest.qWait(300)
        if not window.grab().save(str(output / "dashboard.png")):
            raise RuntimeError("Could not save the dashboard")
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == "__main__":
    main()
