"""Recursive SHA-256 scanner with progress reporting and cooperative cancellation."""
from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple

from ..config import HASH_CHUNK_BYTES, ROOT_EXCLUDES
from .errors import ScanCancelled
from .models import FileEntry, Progress, ScanResult

ProgressCallback = Callable[[Progress], None]


def scan_files(
    root,
    *,
    excludes: Iterable[str] = ROOT_EXCLUDES,
    progress: Optional[ProgressCallback] = None,
    cancel: Optional[threading.Event] = None,
) -> ScanResult:
    """Hash every file under *root*.

    Unreadable files/folders are collected in ``ScanResult.errors`` instead of aborting,
    so callers can decide how strict to be. Raises ScanCancelled if *cancel* is set.
    """
    root_path = Path(root)
    skip = {name.casefold() for name in excludes}
    errors: List[str] = []
    found: List[Tuple[Path, str, int]] = []

    def check_cancel() -> None:
        if cancel is not None and cancel.is_set():
            raise ScanCancelled()

    def relative(path: Path) -> str:
        try:
            return path.relative_to(root_path).as_posix()
        except ValueError:
            return str(path)

    def on_walk_error(exc: OSError) -> None:
        errors.append(f"Cannot list folder '{relative(Path(exc.filename or root_path))}': {exc.strerror or exc}")

    # Phase 1: enumerate (cheap) so phase 2 can report real percentages.
    for current, dirs, files in os.walk(root_path, topdown=True, onerror=on_walk_error):
        check_cancel()
        folder = Path(current)
        if folder == root_path:
            dirs[:] = [d for d in dirs if d.casefold() not in skip]
        for name in files:
            path = folder / name
            rel = relative(path)
            try:
                size = path.stat().st_size
            except OSError as exc:
                errors.append(f"Cannot read '{rel}': {exc.strerror or exc}")
                continue
            found.append((path, rel, size))
        if progress:
            progress(Progress("enumerate", files_total=len(found), current=relative(folder) or "/"))

    total_bytes = sum(size for _, _, size in found)
    total_files = len(found)
    bytes_done = 0
    entries: List[FileEntry] = []
    buffer = memoryview(bytearray(HASH_CHUNK_BYTES))

    # Phase 2: hash.
    for index, (path, rel, _size) in enumerate(found):
        check_cancel()
        digest = hashlib.sha256()
        read_total = 0
        try:
            with path.open("rb", buffering=0) as stream:
                while True:
                    count = stream.readinto(buffer)
                    if not count:
                        break
                    digest.update(buffer[:count])
                    read_total += count
                    bytes_done += count
                    check_cancel()
                    if progress:
                        progress(Progress("hash", index, total_files, bytes_done, total_bytes, rel))
        except OSError as exc:
            errors.append(f"Cannot read '{rel}': {exc.strerror or exc}")
            continue
        entries.append(FileEntry(rel, read_total, digest.hexdigest()))
        if progress:
            progress(Progress("hash", index + 1, total_files, bytes_done, total_bytes, rel))

    entries.sort(key=lambda e: e.path.casefold())
    return ScanResult(entries, errors, total_bytes)
