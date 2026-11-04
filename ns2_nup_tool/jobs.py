"""Qt process lifecycle and progress delivery."""

import json
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal


class JobRunner(QObject):
    progress = Signal(dict)
    finished = Signal(str, dict)
    busy_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.temporary = None
        self.directory = None
        self.operation = ""
        self.offset = 0
        self.timer = QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.poll)

    @property
    def busy(self):
        return self.process is not None

    def start(self, request):
        if self.busy:
            raise RuntimeError("Another operation is already running.")
        self.temporary = tempfile.TemporaryDirectory(prefix="ns2-nup-tool-job-")
        self.directory = Path(self.temporary.name)
        self.operation = request["operation"]
        self.offset = 0
        (self.directory / "request.json").write_text(json.dumps(request), encoding="utf-8")
        self.process = QProcess(self)
        self.process.finished.connect(self.complete)
        self.process.errorOccurred.connect(self.process_error)
        if getattr(sys, "frozen", False):
            args = ["--worker", str(self.directory)]
        else:
            args = [str(Path(__file__).resolve().parent.parent / "main.py"),
                    "--worker", str(self.directory)]
        self.busy_changed.emit(True)
        self.timer.start()
        self.process.start(sys.executable, args)

    def cancel(self):
        if self.busy:
            (self.directory / "cancel").touch()

    def poll(self):
        path = self.directory / "events.jsonl"
        if not path.exists():
            return
        with path.open("rb") as file:
            file.seek(self.offset)
            while line := file.readline():
                if not line.endswith(b"\n"):
                    break
                self.offset = file.tell()
                self.progress.emit(json.loads(line))

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.complete(-1)

    def complete(self, exit_code=0, exit_status=None):
        if not self.busy:
            return
        self.poll()
        path = self.directory / "result.json"
        try:
            result = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
                "status": "error", "message": f"Worker exited unexpectedly (code {exit_code}).",
                "details": self.process.errorString(),
            }
        except (OSError, ValueError) as error:
            result = {"status": "error", "message": f"Cannot read the worker result: {error}"}
        self.timer.stop()
        self.process.deleteLater()
        self.process = None
        self.temporary.cleanup()
        self.temporary = None
        self.busy_changed.emit(False)
        self.finished.emit(self.operation, result)
