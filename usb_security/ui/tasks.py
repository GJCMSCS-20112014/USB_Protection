"""Run one long job on a worker thread and deliver results back on the UI thread.

Scheduler-agnostic: pass `widget.after` (Tk) or any `(ms, callable)` function (tests).
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Optional

from ..core.errors import ScanCancelled
from ..core.models import Progress


class TaskContext:
    """Handed to the job: report progress and observe cancellation."""

    def __init__(self) -> None:
        self.cancel_event = threading.Event()
        self._lock = threading.Lock()
        self._latest: Optional[Progress] = None

    def report(self, progress: Progress) -> None:
        with self._lock:          # keep only the newest value; the UI polls
            self._latest = progress

    def take(self) -> Optional[Progress]:
        with self._lock:
            latest, self._latest = self._latest, None
            return latest


class TaskRunner:
    def __init__(self, schedule: Callable[[int, Callable[[], None]], Any],
                 on_busy: Optional[Callable[[bool], None]] = None, poll_ms: int = 60):
        self._schedule = schedule
        self._on_busy = on_busy
        self._poll_ms = poll_ms
        self._ctx: Optional[TaskContext] = None

    @property
    def busy(self) -> bool:
        return self._ctx is not None

    def cancel(self) -> None:
        if self._ctx is not None:
            self._ctx.cancel_event.set()

    def submit(self, job: Callable[[TaskContext], Any], *,
               on_done: Optional[Callable[[Any], None]] = None,
               on_error: Optional[Callable[[BaseException], None]] = None,
               on_cancel: Optional[Callable[[], None]] = None,
               on_progress: Optional[Callable[[Progress], None]] = None) -> None:
        if self._ctx is not None:
            raise RuntimeError("A task is already running.")
        ctx = TaskContext()
        self._ctx = ctx
        outcome: dict = {}

        def target() -> None:
            try:
                outcome["value"] = ("done", job(ctx))
            except ScanCancelled:
                outcome["value"] = ("cancelled", None)
            except Exception as exc:  # noqa: BLE001 - surfaced to the UI
                outcome["value"] = ("error", exc)

        thread = threading.Thread(target=target, name="usb-security-task", daemon=True)
        if self._on_busy:
            self._on_busy(True)
        thread.start()

        def poll() -> None:
            progress = ctx.take()
            if progress is not None and on_progress:
                on_progress(progress)
            if thread.is_alive():
                self._schedule(self._poll_ms, poll)
                return
            self._ctx = None
            if self._on_busy:
                self._on_busy(False)
            kind, value = outcome.get("value", ("error", RuntimeError("Task ended unexpectedly.")))
            if kind == "done" and on_done:
                on_done(value)
            elif kind == "cancelled" and on_cancel:
                on_cancel()
            elif kind == "error" and on_error:
                on_error(value)

        self._schedule(self._poll_ms, poll)
