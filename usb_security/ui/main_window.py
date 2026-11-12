"""The Tk window. It only draws things and forwards clicks to the Controller."""
from __future__ import annotations

import queue
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Dict, List, Optional

from ..config import APP_NAME, APP_SUBTITLE
from ..core.models import ChangeType, DriveInfo, Progress, RefStatus, VerifyReport
from ..core.utils import ellipsize_middle, human_duration, human_size, open_folder
from .controller import ACTIONS, Controller
from .dialogs import TypedConfirmDialog
from .theme import LIGHT, apply_theme, font, set_titlebar_dark
from .widgets import (ActionTile, Badge, Banner, Card, ChangesTable, DriveTable, KeyValueList,
                      LogView, StatTile, scrolled)


class MainWindow(tk.Tk):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.palette = LIGHT
        self._themed: List = []
        self._tiles: Dict[str, ActionTile] = {}
        self._determinate = False
        self._hash_started = 0.0

        self.title(f"{APP_NAME} \u2014 Integrity Manager")
        width, height = 1220, 800
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        width, height = min(width, screen_w - 60), min(height, screen_h - 100)
        self.geometry(f"{width}x{height}+{(screen_w - width) // 2}+{max(0, (screen_h - height) // 3)}")
        self.minsize(1020, 660)

        apply_theme(self, self.palette)
        self._build()
        self.controller = Controller(ctx, self, self.after)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<F5>", lambda _e: self.controller.refresh())
        set_titlebar_dark(self, False)

        self._pump_log()
        admin = ctx.backend.is_admin()
        ctx.log.info(f"Application Ready. Administrator: {'Yes' if admin else 'No'}")
        self.controller.refresh()

    # ------------------------------------------------------------------ construction
    def _reg(self, widget):
        self._themed.append(widget)
        return widget

    def _build(self) -> None:
        p = self.palette
        self._build_header()

        body = ttk.Frame(self, padding=(28, 10, 28, 6))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=0, minsize=440)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")

        self._build_devices(left)
        self._build_actions(right)
        self._build_results(right)
        self._build_footer()

    def _build_header(self) -> None:
        header = ttk.Frame(self, padding=(28, 20, 28, 6))
        header.pack(fill="x")
        titles = ttk.Frame(header)
        titles.pack(side="left")
        ttk.Label(titles, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(titles, text=APP_SUBTITLE, style="Muted.TLabel").pack(anchor="w")

        tools = ttk.Frame(header)
        tools.pack(side="right")
        admin = self.ctx.backend.is_admin()
        self.admin_badge = self._reg(Badge(tools, self.palette,
                                           "ADMINISTRATOR" if admin else "STANDARD USER",
                                           "success" if admin else "warn"))
        self.admin_badge.pack(side="right", padx=(0, 12))

    def _build_devices(self, parent) -> None:
        p = self.palette
        devices = self._reg(Card(parent, p, "1   Select USB device", "Refresh  (F5)",
                                 lambda: self.controller.refresh()))
        devices.pack(fill="both", expand=True)
        box, self.drive_table = scrolled(devices.body, lambda parent_: DriveTable(parent_, p, self._on_drive_clicked))
        self._reg(self.drive_table)
        box.pack(fill="both", expand=True)
        ttk.Label(devices.body, style="Muted.Card.TLabel", wraplength=390, justify="left",
                  text="Select the USB drive you want to manage. Windows system drives are excluded."
                  ).pack(anchor="w", pady=(10, 0))

        details = self._reg(Card(parent, p, "Selected device"))
        details.pack(fill="x", pady=(14, 0))
        self.usage_label = ttk.Label(details.body, text="Select a device to see its details.",
                                     style="Muted.Card.TLabel")
        self.usage_label.pack(anchor="w")
        self.usage = ttk.Progressbar(details.body, style="Usage.Horizontal.TProgressbar", maximum=100)
        self.usage.pack(fill="x", pady=(6, 12))
        self.details = KeyValueList(details.body, [
            ("drive", "Drive"), ("fs", "File system"), ("serial", "Volume serial"),
            ("bus", "Bus type"), ("protection", "Protection"), ("refs", "References")])
        self.details.pack(fill="x")

    def _build_actions(self, parent) -> None:
        card = self._reg(Card(parent, self.palette, "2   Choose an action"))
        card.pack(fill="x")
        card.body.columnconfigure(0, weight=1, uniform="tiles")
        card.body.columnconfigure(1, weight=1, uniform="tiles")
        for index, spec in enumerate(ACTIONS):
            row, col = divmod(index, 2)
            tile = self._reg(ActionTile(card.body, self.palette, spec.title, spec.subtitle, spec.kind,
                                        lambda key=spec.key: getattr(self.controller, key)()))
            tile.grid(row=row, column=col, sticky="nsew",
                      padx=(0, 6) if col == 0 else (6, 0), pady=(0, 10) if row == 0 else (0, 0))
            self._tiles[spec.key] = tile

    def _build_results(self, parent) -> None:
        p = self.palette
        card = self._reg(Card(parent, p, "3   Results"))
        card.pack(fill="both", expand=True, pady=(14, 0))
        body = card.body

        # progress strip (shown only while a task runs)
        self.progress_frame = ttk.Frame(body, style="Card.TFrame")
        row = ttk.Frame(self.progress_frame, style="Card.TFrame")
        row.pack(fill="x")
        self.task_label = ttk.Label(row, text="", style="Heading.Card.TLabel")
        self.task_label.pack(side="left")
        self.cancel_button = ttk.Button(row, text="Cancel", style="Small.TButton",
                                        command=lambda: self.controller.cancel())
        self.cancel_button.pack(side="right")
        self.progress = ttk.Progressbar(self.progress_frame, style="Accent.Horizontal.TProgressbar",
                                        mode="indeterminate", maximum=100)
        self.progress.pack(fill="x", pady=(8, 4))
        self.progress_detail = ttk.Label(self.progress_frame, text="", style="Muted.Card.TLabel", justify="left")
        self.progress_detail.pack(anchor="w")

        self.banner = self._reg(Banner(body, p))
        self.banner.pack(fill="x")
        self.banner.set("idle", "Ready", "Select a USB device on the left, then choose an action.")

        stats = ttk.Frame(body, style="Card.TFrame")
        stats.pack(fill="x", pady=(12, 0))
        self.stats: Dict[str, StatTile] = {}
        for column, (key, caption) in enumerate((("files", "Files scanned"), ("added", "Added"),
                                                  ("modified", "Modified"), ("deleted", "Deleted"))):
            stats.columnconfigure(column, weight=1, uniform="stats")
            tile = self._reg(StatTile(stats, p, caption))
            tile.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 6, 0 if column == 3 else 6))
            self.stats[key] = tile

        # Keep the live log model available for the footer's Copy log action.
        # The contents are shown on demand in dedicated pop-up windows.
        self.log_view = LogView(body, p)
        self.log_view.pack_forget()
        self._last_changes = []
        self._changes_count = 0

        log_actions = ttk.Frame(body, style="Card.TFrame")
        log_actions.pack(fill="x", pady=(14, 0))
        self.activity_button = ttk.Button(log_actions, text="Activity Log", style="Small.TButton",
                                          command=self._show_activity_log)
        self.activity_button.pack(side="left", padx=(0, 8))
        self.changes_button = ttk.Button(log_actions, text="Changes", style="Small.TButton",
                                         command=self._show_changes)
        self.changes_button.pack(side="left")

    def _build_footer(self) -> None:
        footer = ttk.Frame(self, padding=(28, 6, 28, 16))
        footer.pack(fill="x")
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(footer, textvariable=self.status_var, style="Muted.TLabel").pack(side="left")
        ttk.Button(footer, text="Open logs", style="Small.TButton",
                   command=lambda: self._open(self.ctx.paths.logs)).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="Open PC integrity folder", style="Small.TButton",
                   command=lambda: self._open(self.ctx.paths.integrity)).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="Copy log", style="Small.TButton", command=self._copy_log).pack(side="right")

    # ------------------------------------------------------------------ small helpers
    def _on_drive_clicked(self, index: int) -> None:
        self.controller.select(index)

    def _on_close(self) -> None:
        if self.controller.shutdown():
            self.destroy()

    def _open(self, folder) -> None:
        try:
            open_folder(folder)
        except Exception as exc:  # noqa: BLE001
            self.error("Open folder", str(exc))

    def _show_activity_log(self) -> None:
        popup = tk.Toplevel(self)
        popup.title("Activity Log")
        popup.geometry("900x560")
        popup.transient(self)
        box, view = scrolled(popup, lambda parent_: LogView(parent_, self.palette))
        box.pack(fill="both", expand=True, padx=12, pady=12)
        content = self.log_view.text_content()
        if content:
            view.configure(state="normal")
            view.insert("end", content)
            view.configure(state="disabled")
            view.see("end")
        ttk.Button(popup, text="Close", style="Small.TButton", command=popup.destroy).pack(
            anchor="e", padx=12, pady=(0, 12))

    def _show_changes(self) -> None:
        popup = tk.Toplevel(self)
        popup.title(f"Changes ({self._changes_count})")
        popup.geometry("900x560")
        popup.transient(self)
        box, table = scrolled(popup, lambda parent_: ChangesTable(parent_, self.palette), horizontal=True)
        box.pack(fill="both", expand=True, padx=12, pady=12)
        table.load(self._last_changes)
        if not self._last_changes:
            ttk.Label(popup, text="No file changes to display.", style="Muted.TLabel").pack(anchor="w", padx=14)
        ttk.Button(popup, text="Close", style="Small.TButton", command=popup.destroy).pack(
            anchor="e", padx=12, pady=(0, 12))

    def _copy_log(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.log_view.text_content())
        self.set_status("Log copied to clipboard.")

    def _pump_log(self) -> None:
        try:
            while True:
                event = self.ctx.log_queue.get_nowait()
                self.log_view.append(event.level, event.message, event.stamp)
        except queue.Empty:
            pass
        self.after(100, self._pump_log)

    # ------------------------------------------------------------------ View protocol
    def set_drives(self, drives: List[DriveInfo], selected: Optional[DriveInfo]) -> None:
        self.drive_table.load(drives, selected)

    def set_selected(self, drive: Optional[DriveInfo], refs: Optional[RefStatus]) -> None:
        if drive is None:
            self.details.clear()
            self.usage.configure(value=0)
            self.usage_label.configure(text="Select a device to see its details.")
            return
        pct = (drive.used / drive.total * 100) if drive.total else 0
        self.usage.configure(value=pct)
        self.usage_label.configure(text=f"{human_size(drive.used)} used of {human_size(drive.total)}  ({pct:.0f}%)")
        self.details.set("drive", f"{drive.display_root}   {drive.label}")
        self.details.set("fs", drive.filesystem)
        self.details.set("serial", drive.serial)
        if drive.is_system:
            self.details.set("bus", f"{drive.bus_name}  \u00b7  system drive", "warn")
        else:
            self.details.set("bus", drive.bus_name, "success" if drive.is_usb else "")
        if drive.read_only is True:
            self.details.set("protection", "Read-Only", "success")
        elif drive.read_only is False:
            self.details.set("protection", "Writable" + ("" if drive.protectable else "  \u00b7  locking disabled"))
        else:
            self.details.set("protection", "Unknown", "muted")
        if refs is None:
            self.details.set("refs", "\u2014")
        else:
            mark = lambda ok: "\u2714" if ok else "\u2718"  # noqa: E731
            text = f"PC {mark(refs.pc_found)}      USB {mark(refs.usb_found)}"
            both, none = refs.pc_found and refs.usb_found, not (refs.pc_found or refs.usb_found)
            self.details.set("refs", text if not none else "None created yet",
                             "success" if both else ("muted" if none else "warn"))

    def set_actions_enabled(self, enabled: Dict[str, bool]) -> None:
        for key, tile in self._tiles.items():
            tile.set_enabled(bool(enabled.get(key, False)))

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def begin_task(self, title: str, cancellable: bool) -> None:
        self._determinate = False
        self.task_label.configure(text=title)
        self.progress_detail.configure(text="Starting\u2026")
        self.progress.configure(mode="indeterminate", value=0)
        self.progress.start(14)
        self.cancel_button.configure(state="normal" if cancellable else "disabled")
        self.progress_frame.pack(fill="x", pady=(0, 12), before=self.banner)
        self.banner.set("info", f"{title}\u2026",
                        "You can cancel at any time; nothing is changed until the scan completes."
                        if cancellable else "Please wait\u2026")
        self.set_status(f"{title}\u2026")

    def set_progress(self, p: Progress) -> None:
        if p.phase != "hash":
            self.progress_detail.configure(
                text=f"Scanning folders\u2026  {p.files_total:,} files found\n{ellipsize_middle(p.current, 90)}")
            return
        if not self._determinate:
            self.progress.stop()
            self.progress.configure(mode="determinate", maximum=100, value=0)
            self._determinate = True
            self._hash_started = time.monotonic()
        self.progress.configure(value=(p.fraction or 0) * 100)
        elapsed = max(time.monotonic() - self._hash_started, 0.001)
        speed = p.bytes_done / elapsed
        remaining = (p.bytes_total - p.bytes_done) / speed if speed > 0 and p.bytes_total else None
        line = (f"{p.files_done:,} / {p.files_total:,} files  \u00b7  {human_size(p.bytes_done)} of "
                f"{human_size(p.bytes_total)}  \u00b7  {human_size(speed)}/s")
        if remaining is not None and remaining >= 1:
            line += f"  \u00b7  about {human_duration(remaining)} left"
        self.progress_detail.configure(text=f"{line}\n{ellipsize_middle(p.current, 90)}")

    def end_task(self) -> None:
        self.progress.stop()
        self.progress_frame.pack_forget()

    def show_report(self, report: VerifyReport) -> None:
        reasons = report.failure_reasons()
        if report.passed:
            self.banner.set("success", "Integrity Verified",
                            f"{report.files_scanned:,} files ({human_size(report.bytes_scanned)}) match both "
                            f"references. Checked in {human_duration(report.duration)}.")
        elif not report.scanned:
            self.banner.set("danger", "Cannot Verify",
                            "No integrity reference exists for this drive yet. Create one first, after "
                            "confirming the drive contents are clean.")
        else:
            lines = list(reasons)
            if report.changes:
                lines.append(f"{len(report.changes)} file change(s) detected \u2014 see the Changes tab.")
            self.banner.set("danger", "Integrity Check Failed", "\n".join(f"\u2022 {x}" for x in lines))

        def count(kind: ChangeType) -> int:
            return report.count(kind)

        self.stats["files"].set(report.files_scanned if report.scanned else "\u2014")
        self.stats["added"].set(count(ChangeType.ADDED), "info" if count(ChangeType.ADDED) else "")
        self.stats["modified"].set(count(ChangeType.MODIFIED), "warn" if count(ChangeType.MODIFIED) else "")
        self.stats["deleted"].set(count(ChangeType.DELETED), "danger" if count(ChangeType.DELETED) else "")
        self._last_changes = list(report.changes)
        self._changes_count = len(self._last_changes)
        self.changes_button.configure(text=f"Changes ({self._changes_count})" if self._changes_count else "Changes")

    def show_notice(self, kind: str, title: str, detail: str) -> None:
        self.banner.set(kind, title, detail)

    def info(self, title: str, message: str) -> None:
        messagebox.showinfo(title, message, parent=self)

    def error(self, title: str, message: str) -> None:
        messagebox.showerror(title, message, parent=self)

    def ask_yes_no(self, title: str, message: str) -> bool:
        return bool(messagebox.askyesno(title, message, parent=self))

    def ask_typed(self, title: str, message: str, phrase: str) -> bool:
        return TypedConfirmDialog(self, self.palette, title, message, phrase).show()

    def quit_app(self) -> None:
        self.destroy()
