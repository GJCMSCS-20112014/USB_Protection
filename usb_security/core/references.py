"""Where integrity references live (one copy on the USB, one on this PC)."""
from __future__ import annotations

import os
from pathlib import Path

from ..config import MANIFEST_NAME, META_FOLDER


class ReferenceStore:
    def __init__(self, pc_dir: Path):
        self.pc_dir = Path(pc_dir)

    def usb_path(self, root: str) -> str:
        return os.path.join(root, META_FOLDER, MANIFEST_NAME)

    def pc_path(self, serial: str) -> str:
        return str(self.pc_dir / f"{serial}.csv")
