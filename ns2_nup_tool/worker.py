"""A single cancellable job per process; file IPC also works in windowed builds."""

from __future__ import annotations

import json
import time
import traceback
from pathlib import Path

from .backend import Cancelled, run_operation


def run_job(directory):
    directory = Path(directory)
    last_report = 0.0

    def check():
        if (directory / "cancel").exists():
            raise Cancelled("Operation cancelled. No incomplete output was published.")

    def report(done, total, message):
        nonlocal last_report
        check()
        now = time.monotonic()
        if now - last_report < 0.15 and not (total > 0 and done == total):
            return
        last_report = now
        with (directory / "events.jsonl").open("a", encoding="utf-8") as file:
            file.write(json.dumps({"done": done, "total": total, "message": message}) + "\n")

    try:
        request = json.loads((directory / "request.json").read_text(encoding="utf-8"))
        result = {"status": "ok", "result": run_operation(request, check, report)}
    except Cancelled as error:
        result = {"status": "cancelled", "message": str(error)}
    except (Exception, SystemExit) as error:
        result = {"status": "error", "message": str(error), "details": traceback.format_exc()}
    (directory / "result.json").write_text(json.dumps(result, ensure_ascii=True), encoding="utf-8")
    return 0 if result["status"] == "ok" else 1
