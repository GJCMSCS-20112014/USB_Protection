"""Use-cases: create references and verify a drive. Pure logic, fully unit-testable."""
from __future__ import annotations

import os
import threading
import time
from typing import Callable, Optional

from .errors import ScanIncompleteError
from .manifest import diff, manifests_match, read_manifest, write_manifest
from .models import CreateResult, DriveInfo, RefStatus, VerifyReport
from .references import ReferenceStore
from .scanner import ProgressCallback, scan_files

Scanner = Callable[..., object]


class IntegrityService:
    def __init__(self, store: ReferenceStore, scanner: Scanner = scan_files):
        self.store = store
        self._scan = scanner

    def reference_status(self, drive: DriveInfo) -> RefStatus:
        return RefStatus(
            pc_found=os.path.isfile(self.store.pc_path(drive.serial)),
            usb_found=os.path.isfile(self.store.usb_path(drive.root)),
        )

    def create(self, drive: DriveInfo, *, progress: Optional[ProgressCallback] = None,
               cancel: Optional[threading.Event] = None) -> CreateResult:
        started = time.monotonic()
        scan = self._scan(drive.root, progress=progress, cancel=cancel)
        if scan.errors:
            # A reference with holes in it would give false confidence later.
            raise ScanIncompleteError(scan.errors)
        usb_path = self.store.usb_path(drive.root)
        pc_path = self.store.pc_path(drive.serial)
        # USB first: if the drive is read-only/locked we fail before touching the PC copy.
        write_manifest(usb_path, scan.entries)
        write_manifest(pc_path, scan.entries)
        return CreateResult(len(scan.entries), scan.total_bytes, usb_path, pc_path,
                            time.monotonic() - started)

    def verify(self, drive: DriveInfo, *, progress: Optional[ProgressCallback] = None,
               cancel: Optional[threading.Event] = None) -> VerifyReport:
        started = time.monotonic()
        usb_path = self.store.usb_path(drive.root)
        pc_path = self.store.pc_path(drive.serial)
        pc_rows = read_manifest(pc_path) if os.path.isfile(pc_path) else None
        usb_rows = read_manifest(usb_path) if os.path.isfile(usb_path) else None
        report = VerifyReport(pc_path, usb_path, pc_rows is not None, usb_rows is not None)

        if pc_rows is not None and usb_rows is not None:
            report.refs_match = manifests_match(pc_rows, usb_rows)

        if pc_rows is not None or usb_rows is not None:
            scan = self._scan(drive.root, progress=progress, cancel=cancel)
            report.scanned = True
            report.scan_errors = list(scan.errors)
            report.files_scanned = len(scan.entries)
            report.bytes_scanned = scan.total_bytes
            if pc_rows is not None:
                report.actual_matches_pc = manifests_match(pc_rows, scan.entries)
            if usb_rows is not None:
                report.actual_matches_usb = manifests_match(usb_rows, scan.entries)
            baseline_rows, report.baseline = ((pc_rows, "LOCAL_PC") if pc_rows is not None
                                              else (usb_rows, "SAVED_USB"))
            report.changes = diff(baseline_rows, scan.entries)

        report.duration = time.monotonic() - started
        return report
