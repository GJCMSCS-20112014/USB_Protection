"""Activity log: one logger fanned out to a daily log file and to the UI (via a queue)."""
from __future__ import annotations

import logging
import queue
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

PASS = 25
logging.addLevelName(PASS, "PASS")

_TAGS = {"DEBUG": "INFO", "INFO": "INFO", "PASS": "PASS", "WARNING": "WARN",
         "ERROR": "FAIL", "CRITICAL": "FAIL"}


class LogEvent(NamedTuple):
    level: str    # INFO | PASS | WARN | FAIL
    message: str
    stamp: str    # HH:MM:SS


class _DailyFileHandler(logging.Handler):
    """Appends to USB_App_YYYYMMDD.log, re-resolving the file name on every record."""

    def __init__(self, directory: Path):
        super().__init__()
        self.directory = Path(directory)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            stamp = datetime.fromtimestamp(record.created)
            path = self.directory / f"USB_App_{stamp:%Y%m%d}.log"
            line = f"[{stamp:%Y-%m-%d %H:%M:%S}] [{_TAGS.get(record.levelname, 'INFO')}] {record.getMessage()}\n"
            with path.open("a", encoding="utf-8") as stream:
                stream.write(line)
        except OSError:
            pass


class _QueueHandler(logging.Handler):
    def __init__(self, sink: "queue.Queue[LogEvent]"):
        super().__init__()
        self.sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        stamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        self.sink.put(LogEvent(_TAGS.get(record.levelname, "INFO"), record.getMessage(), stamp))


class ActivityLog:
    """Thread-safe facade: info / ok / warn / fail."""

    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def info(self, message: str) -> None: self._logger.info(message)
    def ok(self, message: str) -> None: self._logger.log(PASS, message)
    def warn(self, message: str) -> None: self._logger.warning(message)
    def fail(self, message: str) -> None: self._logger.error(message)


def build_activity_log(log_dir: Path, name: str = "usb_security"):
    """Return (ActivityLog, queue the UI should drain)."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    sink: "queue.Queue[LogEvent]" = queue.Queue()
    logger.addHandler(_DailyFileHandler(log_dir))
    logger.addHandler(_QueueHandler(sink))
    return ActivityLog(logger), sink
