"""NS2 NUP Tool GUI entry point and packaged worker dispatch."""

import sys


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        from ns2_nup_tool.worker import run_job
        return run_job(sys.argv[2])
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        import json
        import os
        import tempfile
        import traceback
        from pathlib import Path
        report = Path(sys.argv[2])
        try:
            os.environ["QT_QPA_PLATFORM"] = "offscreen"
            from PySide6.QtWidgets import QApplication
            from PySide6.QtCore import QCoreApplication, QEvent, QSettings, QTimer
            from ns2_nup_tool.app import MainWindow, STYLE
            from ns2_nup_tool.eshop_dialog import ShopDialog
            application = QApplication([])
            application.setStyleSheet(STYLE)
            with tempfile.TemporaryDirectory(prefix="nup-gui-smoke-") as settings_dir:
                settings = QSettings(str(Path(settings_dir) / "settings.ini"), QSettings.Format.IniFormat)
                window = MainWindow(settings)
                window.show()
                assert window.pages.count() == 3
                shop = ShopDialog("Smoke test", "", {"name", "publisher", "icon"}, window)
                assert not shop.runner.busy
                QTimer.singleShot(40, lambda: window.nav.setCurrentRow(0))
                QTimer.singleShot(300, window.show_home)
                QTimer.singleShot(560, lambda: window.nav.setCurrentRow(1))
                QTimer.singleShot(820, window.close)
                application.exec()
                window.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                settings.sync()
            result = {"status": "ok", "message": "Qt DLLs loaded; retro pages and shop constructed; animated navigation and clean shutdown checked."}
        except Exception:
            result = {"status": "error", "details": traceback.format_exc()}
        report.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return 0 if result["status"] == "ok" else 1
    from ns2_nup_tool.app import run_app
    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())
