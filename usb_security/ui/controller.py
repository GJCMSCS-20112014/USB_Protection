"""UI-agnostic application logic: what happens when the user clicks something.

The view (Tk window) only has to implement the `View` protocol below, which keeps all of the
workflow - confirmations, admin checks, safety gates, logging - testable without a display.
To add a feature: append an ActionSpec to ACTIONS and add a method with the same name here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Protocol

from ..core.errors import DeviceError, ScanIncompleteError
from ..core.models import ChangeType, CreateResult, DriveInfo, Progress, RefStatus, VerifyReport
from ..core.reports import save_change_report
from ..core.utils import human_duration, human_size
from .tasks import TaskContext, TaskRunner


@dataclass(frozen=True)
class ActionSpec:
    key: str        # also the Controller method name
    title: str
    subtitle: str
    kind: str       # accent | success | warn | danger  (stripe colour)


ACTIONS = (
    ActionSpec("create", "Create Integrity",
               "Snapshot the current files as the trusted reference (PC + USB copy).", "accent"),
    ActionSpec("verify", "Verify Integrity",
               "Re-hash the drive and compare it with both references.", "success"),
    ActionSpec("lock", "Lock USB",
               "Verify first, then set the physical disk read-only.", "warn"),
    ActionSpec("unlock", "Unlock USB",
               "Clear the read-only flag (requires typed confirmation).", "danger"),
)


class View(Protocol):  # what the controller needs from a window
    def set_drives(self, drives: List[DriveInfo], selected: Optional[DriveInfo]) -> None: ...
    def set_selected(self, drive: Optional[DriveInfo], refs: Optional[RefStatus]) -> None: ...
    def set_actions_enabled(self, enabled: Dict[str, bool]) -> None: ...
    def set_status(self, text: str) -> None: ...
    def begin_task(self, title: str, cancellable: bool) -> None: ...
    def set_progress(self, progress: Progress) -> None: ...
    def end_task(self) -> None: ...
    def show_report(self, report: VerifyReport) -> None: ...
    def show_notice(self, kind: str, title: str, detail: str) -> None: ...
    def info(self, title: str, message: str) -> None: ...
    def error(self, title: str, message: str) -> None: ...
    def ask_yes_no(self, title: str, message: str) -> bool: ...
    def ask_typed(self, title: str, message: str, phrase: str) -> bool: ...
    def quit_app(self) -> None: ...


class Controller:
    def __init__(self, ctx, view: View, schedule: Callable[[int, Callable[[], None]], object]):
        self.ctx = ctx
        self.view = view
        self.log = ctx.log
        self.backend = ctx.backend
        self.service = ctx.integrity
        self.runner = TaskRunner(schedule, on_busy=self._on_busy)
        self.drives: List[DriveInfo] = []
        self.selected: Optional[DriveInfo] = None

    # ------------------------------------------------------------------ devices
    @property
    def busy(self) -> bool:
        return self.runner.busy

    def refresh(self) -> None:
        if self.busy:
            return
        previous = self.selected.key if self.selected else None
        try:
            # Never expose Windows/system volumes (including C:) as selectable targets.
            self.drives = [d for d in self.backend.list_drives() if not d.is_system]
        except Exception as exc:  # noqa: BLE001
            self.drives = []
            self.log.fail(f"Could not List Drives: {exc}")
        self.selected = next((d for d in self.drives if d.key == previous), None)
        self.view.set_drives(self.drives, self.selected)
        self._push_selection()
        self.view.set_status("Drive List Refreshed.")
        self.log.info(f"{len(self.drives)} mounted drive(s) listed. Manually select your USB.")

    def select(self, index: int) -> None:
        if self.busy:                                   # selection is locked while a task runs
            self.view.set_drives(self.drives, self.selected)
            return
        if 0 <= index < len(self.drives) and not self.drives[index].is_system:
            self.selected = self.drives[index]
            d = self.selected
            self.log.info(f"Manually selected {d.display_root} (volume serial {d.serial}).")
            self._push_selection()

    def _push_selection(self) -> None:
        refs = self.service.reference_status(self.selected) if self.selected else None
        self.view.set_selected(self.selected, refs)
        self._update_actions()

    def _update_actions(self) -> None:
        d = self.selected
        ready = d is not None and not self.busy
        self.view.set_actions_enabled({
            "create": ready, "verify": ready,
            "lock": ready and d.protectable, "unlock": ready and d.protectable,
        })

    def _on_busy(self, busy: bool) -> None:
        self._update_actions()

    def _require_drive(self) -> Optional[DriveInfo]:
        if self.selected is None:
            self.view.info("Select USB", "Please manually select a USB drive first.")
        return self.selected

    # ------------------------------------------------------------------ task plumbing
    def _run(self, title: str, job: Callable[[TaskContext], object],
             on_done: Callable[[object], None], cancellable: bool = True) -> None:
        self.log.info(f"\u25b6 {title}")
        self.view.begin_task(title, cancellable)

        def done(result):
            self.view.end_task()
            on_done(result)

        def failed(exc: BaseException):
            self.view.end_task()
            self._report_error(title, exc)

        def cancelled():
            self.view.end_task()
            self.log.warn(f"{title} Cancelled. No changes were made.")
            self.view.show_notice("warn", "Cancelled", f"{title} was Cancelled.")
            self.view.set_status("Cancelled")

        self.runner.submit(job, on_done=done, on_error=failed, on_cancel=cancelled,
                           on_progress=self.view.set_progress)

    def _report_error(self, title: str, exc: BaseException) -> None:
        detail = str(exc)
        if isinstance(exc, ScanIncompleteError):
            shown = "\n".join(exc.errors[:10])
            more = f"\n\u2026 and {len(exc.errors) - 10} more" if len(exc.errors) > 10 else ""
            detail = f"{exc}\n\n{shown}{more}\n\nNothing was saved."
            for line in exc.errors:
                self.log.warn(line)
        self.log.fail(f"{title.upper()} FAILED: {exc}")
        self.view.set_status(f"{title} failed")
        self.view.show_notice("danger", f"{title} failed", str(exc).splitlines()[0] if str(exc) else "")
        self.view.error(f"{title} failed", detail)

    def cancel(self) -> None:
        if self.busy:
            self.log.warn("Cancelling\u2026")
            self.runner.cancel()

    def shutdown(self) -> bool:
        """Called on window close. Returns True if the window may close."""
        if self.busy:
            if not self.view.ask_yes_no("Task running", "A task is still running. Cancel it and exit?"):
                return False
            self.runner.cancel()
        return True

    # ------------------------------------------------------------------ actions
    def create(self) -> None:
        drive = self._require_drive()
        if not drive:
            return
        if not self.view.ask_yes_no(
                "Create Integrity References",
                f"Create or replace both integrity references from {drive.display_root}?\n\n"
                "Only continue after checking that the USB contents are clean."):
            return
        self._run("Creating Integrity References",
                  lambda ctx: self.service.create(drive, progress=ctx.report, cancel=ctx.cancel_event),
                  lambda result: self._create_done(result))

    def _create_done(self, result: CreateResult) -> None:
        self.log.ok(f"Created integrity references for {result.file_count} files "
                    f"({human_size(result.total_bytes)}) in {human_duration(result.duration)}.")
        self.log.info(f"SAVED_USB INTEGRITY REFERENCE: {result.usb_path}")
        self.log.info(f"LOCAL_PC INTEGRITY REFERENCE: {result.pc_path}")
        self.view.set_status("Integrity References Created.")
        self.view.show_notice("success", "Integrity References Created",
                              f"{result.file_count:,} files \u00b7 {human_size(result.total_bytes)} \u00b7 "
                              f"saved to the USB and to this PC")
        self._push_selection()

    def verify(self) -> None:
        self._start_verify(None)

    def _start_verify(self, then: Optional[Callable[[VerifyReport], None]]) -> None:
        drive = self._require_drive()
        if not drive:
            return
        self._run("Verifying Integrity", lambda ctx: self._verify_job(drive, ctx),
                  lambda result: self._verify_done(result, then))

    def _verify_job(self, drive: DriveInfo, ctx: TaskContext):
        report = self.service.verify(drive, progress=ctx.report, cancel=ctx.cancel_event)
        saved = None
        if report.scanned:
            try:
                saved = save_change_report(self.ctx.paths.logs, report.changes)
            except OSError as exc:
                self.log.warn(f"Could not save change report: {exc}")
        return report, saved

    def _verify_done(self, result, then) -> None:
        report, saved = result
        self._log_report(report, saved)
        self.view.show_report(report)
        self.view.set_status("Integrity Verified" if report.passed else "Integrity Check Failed")
        self._push_selection()
        if then:
            then(report)

    def _log_report(self, r: VerifyReport, saved) -> None:
        self.log.info("INTEGRITY REFERENCE STATUS")
        for found, label, path in ((r.pc_found, "LOCAL_PC", r.pc_path), (r.usb_found, "SAVED_USB", r.usb_path)):
            line = f"[{'FOUND' if found else 'NOT FOUND'}] {label} INTEGRITY REFERENCE: {path}"
            (self.log.ok if found else self.log.fail)(line)
        self.log.info("INTEGRITY REFERENCE COMPARISON")
        if r.refs_match is None:
            self.log.warn("[NOT CHECKED] Comparison requires both integrity references.")
        elif r.refs_match:
            self.log.ok("[PASS] LOCAL_PC matches SAVED_USB INTEGRITY REFERENCE.")
        else:
            self.log.fail("[FAIL] LOCAL_PC does NOT MATCH SAVED_USB INTEGRITY REFERENCE.")
        for matched, label in ((r.actual_matches_pc, "LOCAL_PC"), (r.actual_matches_usb, "SAVED_USB")):
            if matched is True:
                self.log.ok(f"[PASS] ACTUAL_USB_FILES match {label} INTEGRITY REFERENCE.")
            elif matched is False:
                self.log.fail(f"[FAIL] ACTUAL_USB_FILES do NOT MATCH {label} INTEGRITY REFERENCE.")
        if r.scanned:
            self.log.info(f"FILE CHANGE REPORT (compared with {r.baseline} INTEGRITY REFERENCE)")
            self.log.info(f"ADDED: {r.count(ChangeType.ADDED)}   MODIFIED: {r.count(ChangeType.MODIFIED)}"
                          f"   DELETED: {r.count(ChangeType.DELETED)}")
            for c in r.changes:
                extra = (f" (size: {c.old_length} -> {c.new_length} bytes)"
                         if c.kind is ChangeType.MODIFIED else "")
                self.log.warn(f"[{c.kind.value}] {c.path}{extra}")
            if not r.changes:
                self.log.ok("[PASS] No file changes detected.")
            for err in r.scan_errors:
                self.log.fail(f"[UNREADABLE] {err}")
            if saved:
                self.log.info(f"Change report saved: {saved}")
        else:
            self.log.warn("[NOT FOUND] Neither integrity reference exists. File change report skipped.")
        verdict = "PASS" if r.passed else "FAIL"
        (self.log.ok if r.passed else self.log.fail)(
            f"INTEGRITY RESULT: {verdict}  ({r.files_scanned:,} files, {human_size(r.bytes_scanned)}, "
            f"{human_duration(r.duration)})")

    # -- lock / unlock
    def lock(self) -> None:
        self._protect(True)

    def unlock(self) -> None:
        self._protect(False)

    def _ensure_admin(self) -> bool:
        if self.backend.is_admin():
            return True
        if self.view.ask_yes_no("Administrator permission",
                                "This operation requires Administrator rights. Restart as Administrator?"):
            if self.backend.restart_as_admin():
                self.view.quit_app()
        return False

    def _protect(self, enable: bool) -> None:
        drive = self._require_drive()
        if not drive or not self._ensure_admin():
            return
        word = "LOCK" if enable else "UNLOCK"
        try:
            target = self.backend.check_protectable(drive)
        except DeviceError as exc:
            self.log.fail(f"{word} FAILED: {exc}")
            self.view.show_notice("danger", f"{word.title()} blocked", str(exc))
            self.view.error("USB protection blocked", str(exc))
            return
        if enable:   # integrity gate: never lock a drive that does not verify
            self._start_verify(lambda report: self._lock_after_verify(drive, target, report))
        else:
            self._confirm_and_apply(drive, target, False)

    def _lock_after_verify(self, drive: DriveInfo, target: str, report: VerifyReport) -> None:
        if not report.passed:
            reasons = "\n".join(f"\u2022 {r}" for r in report.failure_reasons()) or "See the Changes Tab."
            self.log.fail("LOCK BLOCKED: Integrity Verification Failed. USB will not be Locked.")
            self.view.show_notice("danger", "Lock Blocked", "Integrity Verification Failed. The USB was not Locked.")
            self.view.error("Lock Blocked", f"Integrity Verification Failed. USB will not be Locked.\n\n{reasons}")
            return
        self._confirm_and_apply(drive, target, True)

    def _confirm_and_apply(self, drive: DriveInfo, target: str, enable: bool) -> None:
        word = "LOCK" if enable else "UNLOCK"
        action = "set" if enable else "clear read-only on"
        suffix = " read-only" if enable else ""
        if not self.view.ask_typed(f"Confirm {word}", f"Type {word} exactly to {action} {target}{suffix}.", word):
            self.log.warn(f"{word.title()} Cancelled. No disk changes were made.")
            self.view.show_notice("warn", f"{word.title()} Cancelled", "No disk changes were made.")
            return
        self._run(("Locking" if enable else "Unlocking") + " USB",
                  lambda ctx: self.backend.set_read_only(drive, enable),
                  lambda state: self._protect_done(enable, bool(state)), cancellable=False)

    def _protect_done(self, enable: bool, state: bool) -> None:
        text = "Yes" if state else "No"
        self.log.ok(f"{'LOCK' if enable else 'UNLOCK'} CONFIRMED: Read-Only: {text}")
        if enable:
            self.log.info("Safely eject the USB before disconnecting it.")
        self.view.set_status(f"Read-only: {text}")
        self.view.show_notice("success", "USB Locked (Read-Only)" if enable else "USB Unlocked (Writable)",
                              "Windows confirms the disk is read-only. Safely eject before unplugging."
                              if enable else "Windows confirms the read-only flag is cleared.")
        self.refresh()
