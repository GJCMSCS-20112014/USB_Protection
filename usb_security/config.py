"""Application-wide constants and filesystem locations (no I/O at import time)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "USB Security"
APP_SUBTITLE = "Integrity manager  \u00b7  SHA-256  \u00b7  offline"

# Folder created on the USB that holds its copy of the integrity reference.
META_FOLDER = ".USBIntegrity"
MANIFEST_NAME = "integrity.csv"
# Folder name of this program when it is stored on the USB itself.
PROGRAM_FOLDER = "USB_Protection"

# Root-level folders that are never scanned (compared case-insensitively).
ROOT_EXCLUDES = frozenset(
    name.casefold()
    for name in (META_FOLDER, PROGRAM_FOLDER, "System Volume Information", "$RECYCLE.BIN")
)

# Column order of integrity.csv. Unchanged from v1 so existing references keep working.
MANIFEST_FIELDS = ("RelativePath", "Length", "SHA256")

HASH_CHUNK_BYTES = 4 * 1024 * 1024
LOG_MAX_LINES = 5000


@dataclass(frozen=True)
class Paths:
    """Where the program keeps its data. Override with the USB_SECURITY_HOME env var."""

    base: Path

    @classmethod
    def default(cls) -> "Paths":
        override = os.environ.get("USB_SECURITY_HOME")
        return cls(Path(override) if override else Path.home() / "Documents" / "USBProtection")

    @property
    def integrity(self) -> Path:
        return self.base / "Integrity"

    @property
    def logs(self) -> Path:
        return self.base / "Logs"

    @property
    def settings_file(self) -> Path:
        return self.base / "settings.json"
