"""Small helpers shared by core and UI."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def human_size(num_bytes: float) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"  # pragma: no cover


def human_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def ellipsize_middle(text: str, limit: int = 90) -> str:
    if len(text) <= limit:
        return text
    right = (limit - 1) // 2
    left = limit - 1 - right
    return f"{text[:left]}\u2026{text[-right:]}"


def open_folder(folder: Path) -> None:
    """Open a folder in the platform file manager (creating it first)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(folder))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(folder)])
    else:
        subprocess.Popen(["xdg-open", str(folder)])
