"""Composition root: builds the objects once and starts the window."""
from __future__ import annotations

import argparse
import ctypes
import os
import queue
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import __version__
from .config import Paths
from .core.references import ReferenceStore
from .core.service import IntegrityService
from .device import create_backend
from .device.base import DeviceBackend
from .logging_setup import ActivityLog, build_activity_log
from .settings import Settings
from .device.winapi import is_admin, relaunch_as_admin


@dataclass
class AppContext:
    paths: Paths
    settings: Settings
    log: ActivityLog
    log_queue: "queue.Queue"
    backend: DeviceBackend
    integrity: IntegrityService


def build_context(home: Optional[Path] = None) -> AppContext:
    paths = Paths(Path(home)) if home is not None else Paths.default()
    log, log_queue = build_activity_log(paths.logs)
    backend = create_backend()
    return AppContext(paths=paths, settings=Settings.load(paths.settings_file), log=log, log_queue=log_queue,
                      backend=backend, integrity=IntegrityService(ReferenceStore(paths.integrity)))


def _enable_dpi_awareness() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # crisp text on high-DPI screens
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="USB_Security", description="USB integrity manager.")
    parser.add_argument("--home", type=Path, help="folder for references, logs and settings")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    if os.name != "nt":
        print("This application is designed for Windows and requires real USB storage devices.",
              file=sys.stderr)
        return 1

    # The application always starts elevated. If the user declines the Windows UAC
    # prompt (or elevation fails), close this instance without opening the UI.
    if not is_admin():
        if relaunch_as_admin():
            return 0  # The elevated process was launched; close this unelevated one.
        try:
            ctypes.windll.user32.MessageBoxW(
                None,
                "Administrator permission was not granted. USB Protection will now close.",
                "USB Protection - Administrator Required",
                0x10,  # MB_ICONERROR
            )
        except Exception:
            pass
        return 1

    _enable_dpi_awareness()
    context = build_context(home=args.home)
    from .ui.main_window import MainWindow  # imported late so tests never need tkinter
    MainWindow(context).mainloop()
    return 0
