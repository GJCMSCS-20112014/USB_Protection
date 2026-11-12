"""Backend contract. To support another OS or a fake device, implement this and nothing else."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from ..core.models import DriveInfo


class DeviceBackend(ABC):
    name = "abstract"

    @abstractmethod
    def list_drives(self) -> List[DriveInfo]:
        """Mounted fixed/removable volumes, best-effort enriched with bus/system/read-only info."""

    @abstractmethod
    def check_protectable(self, drive: DriveInfo) -> str:
        """Run every safety rule for Lock/Unlock.

        Returns a human description of the target disk, or raises BlockedError / DeviceError.
        """

    @abstractmethod
    def set_read_only(self, drive: DriveInfo, enabled: bool) -> bool:
        """Apply the read-only flag and return the state the OS actually confirms."""

    def is_admin(self) -> bool:
        return True

    def restart_as_admin(self) -> bool:
        return False
