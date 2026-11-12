"""Plain data objects passed between layers. No behaviour beyond simple properties."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

BUS_USB = 7
BUS_NAMES = {
    0: "Unknown", 1: "SCSI", 2: "ATAPI", 3: "ATA", 4: "IEEE 1394", 5: "SSA", 6: "Fibre",
    7: "USB", 8: "RAID", 9: "iSCSI", 10: "SAS", 11: "SATA", 12: "SD", 13: "MMC",
    14: "Virtual", 15: "File-backed virtual", 16: "Storage Spaces", 17: "NVMe",
    18: "SCM", 19: "UFS",
}


class ChangeType(str, Enum):
    ADDED = "ADDED"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"


@dataclass(frozen=True)
class FileEntry:
    path: str          # relative, forward slashes
    length: int
    sha256: str        # lower-case hex


@dataclass(frozen=True)
class Change:
    kind: ChangeType
    path: str
    old_length: Optional[int] = None
    new_length: Optional[int] = None
    old_sha256: str = ""
    new_sha256: str = ""


@dataclass(frozen=True)
class Progress:
    phase: str                 # "enumerate" | "hash"
    files_done: int = 0
    files_total: int = 0
    bytes_done: int = 0
    bytes_total: int = 0
    current: str = ""

    @property
    def fraction(self) -> Optional[float]:
        if self.phase != "hash":
            return None
        if self.bytes_total > 0:
            return min(1.0, self.bytes_done / self.bytes_total)
        if self.files_total > 0:
            return min(1.0, self.files_done / self.files_total)
        return 1.0


@dataclass
class ScanResult:
    entries: List[FileEntry]
    errors: List[str] = field(default_factory=list)
    total_bytes: int = 0


@dataclass(frozen=True)
class DriveInfo:
    letter: str
    root: str                   # path used for scanning, e.g. "E:\\"
    label: str
    filesystem: str
    serial: str                 # volume serial, e.g. "1A2B3C4D"
    total: int
    free: int
    bus_type: Optional[int] = None
    is_system: bool = False
    read_only: Optional[bool] = None

    @property
    def key(self):
        return (self.letter, self.serial)

    @property
    def display_root(self) -> str:
        return f"{self.letter}:"

    @property
    def used(self) -> int:
        return max(0, self.total - self.free)

    @property
    def is_usb(self) -> bool:
        return self.bus_type == BUS_USB

    @property
    def bus_name(self) -> str:
        return "Unknown" if self.bus_type is None else BUS_NAMES.get(self.bus_type, f"Type {self.bus_type}")

    @property
    def protectable(self) -> bool:
        """Whether Lock/Unlock should be offered (the backend still enforces the real rules)."""
        return not self.is_system and (self.bus_type is None or self.is_usb)


@dataclass(frozen=True)
class RefStatus:
    pc_found: bool
    usb_found: bool


@dataclass
class CreateResult:
    file_count: int
    total_bytes: int
    usb_path: str
    pc_path: str
    duration: float = 0.0


@dataclass
class VerifyReport:
    pc_path: str
    usb_path: str
    pc_found: bool
    usb_found: bool
    refs_match: Optional[bool] = None
    actual_matches_pc: Optional[bool] = None
    actual_matches_usb: Optional[bool] = None
    baseline: str = ""                      # "LOCAL_PC" | "SAVED_USB" | ""
    changes: List[Change] = field(default_factory=list)
    scanned: bool = False
    files_scanned: int = 0
    bytes_scanned: int = 0
    scan_errors: List[str] = field(default_factory=list)
    duration: float = 0.0

    def count(self, kind: ChangeType) -> int:
        return sum(1 for c in self.changes if c.kind is kind)

    def failure_reasons(self) -> List[str]:
        reasons: List[str] = []
        if not self.pc_found:
            reasons.append("LOCAL_PC integrity reference not found.")
        if not self.usb_found:
            reasons.append("SAVED_USB integrity reference not found.")
        if self.refs_match is False:
            reasons.append("LOCAL_PC and SAVED_USB references do not match.")
        if self.actual_matches_pc is False:
            reasons.append("USB files differ from the LOCAL_PC reference.")
        if self.actual_matches_usb is False:
            reasons.append("USB files differ from the SAVED_USB reference.")
        if self.scan_errors:
            reasons.append(f"{len(self.scan_errors)} item(s) could not be read, so integrity cannot be confirmed.")
        return reasons

    @property
    def passed(self) -> bool:
        return self.scanned and not self.failure_reasons()
