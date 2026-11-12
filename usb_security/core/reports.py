"""Exporting change reports."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from .models import Change


def save_change_report(log_dir: Path, changes: Iterable[Change], when: Optional[datetime] = None) -> Path:
    when = when or datetime.now()
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"USB_Changes_{when:%Y%m%d_%H%M%S}.csv"
    rows = [
        (c.kind.value, c.path,
         "" if c.old_length is None else c.old_length,
         "" if c.new_length is None else c.new_length,
         c.old_sha256, c.new_sha256)
        for c in changes
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(["Status", "RelativePath", "PreviousLength", "CurrentLength",
                         "PreviousSHA256", "CurrentSHA256"])
        writer.writerows(rows or [("NO CHANGES", "", "", "", "", "")])
    return path
