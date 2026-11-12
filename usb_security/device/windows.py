"""Windows backend: maps volumes -> physical disks and enforces the safety rules."""
from __future__ import annotations

import os
import shutil
from typing import List, Optional, Set

from ..core.errors import AdminRequiredError, BlockedError, DeviceError
from ..core.models import BUS_USB, DriveInfo
from . import winapi
from .base import DeviceBackend


class WindowsBackend(DeviceBackend):
    name = "windows"

    def is_admin(self) -> bool:
        return winapi.is_admin()

    def restart_as_admin(self) -> bool:
        return winapi.relaunch_as_admin()

    # -- discovery ------------------------------------------------------------------------
    def list_drives(self) -> List[DriveInfo]:
        try:
            system_disks = self._system_disks()
        except OSError:
            system_disks = set()
        system_letter = os.environ.get("SystemDrive", "C:")[:1].upper()
        drives: List[DriveInfo] = []
        for letter, root, _dtype in winapi.list_logical_drives():
            try:
                total, _used, free = shutil.disk_usage(root)
            except OSError:
                continue  # empty card-reader slot, locked BitLocker volume, ...
            label, fs, serial = winapi.volume_info(root)
            bus: Optional[int] = None
            read_only: Optional[bool] = None
            is_system = letter == system_letter
            try:
                numbers = winapi.volume_disk_numbers(root)
                is_system = is_system or bool(set(numbers) & system_disks)
                if len(numbers) == 1:
                    bus = winapi.query_disk_descriptor(numbers[0]).bus_type
                    read_only = winapi.get_read_only(numbers[0])
            except OSError:
                pass  # leave unknown; Lock/Unlock still re-checks strictly
            drives.append(DriveInfo(letter, root, label or "No label", fs or "Unknown", serial,
                                    total, free, bus, is_system, read_only))
        return drives

    def _system_disks(self) -> Set[int]:
        return set(winapi.volume_disk_numbers(os.environ.get("SystemDrive", "C:") + "\\"))

    # -- protection -----------------------------------------------------------------------
    def _resolve(self, drive: DriveInfo):
        """Strict safety rules; fail closed if anything cannot be determined."""
        try:
            numbers = winapi.volume_disk_numbers(drive.root)
            if len(numbers) != 1:
                raise BlockedError("BLOCKED: the selected volume spans multiple physical disks.")
            number = numbers[0]
            try:
                system = self._system_disks()
            except OSError as exc:
                raise BlockedError(f"BLOCKED: cannot determine which disk holds Windows ({exc}).") from exc
            if number in system:
                raise BlockedError("BLOCKED: the selected physical disk also contains the Windows system volume.")
            descriptor = winapi.query_disk_descriptor(number)
            if descriptor.bus_type != BUS_USB:
                raise BlockedError("BLOCKED: Windows does not identify the selected physical disk as USB.")
            return number, descriptor
        except OSError as exc:
            raise DeviceError(str(exc)) from exc

    def check_protectable(self, drive: DriveInfo) -> str:
        number, descriptor = self._resolve(drive)
        name = " ".join(part for part in (descriptor.vendor, descriptor.product) if part)
        return f"physical disk {number}" + (f" ({name})" if name else "")

    def set_read_only(self, drive: DriveInfo, enabled: bool) -> bool:
        if not self.is_admin():
            raise AdminRequiredError("Administrator rights are required.")
        number, _ = self._resolve(drive)
        try:
            actual = winapi.set_read_only(number, enabled)
        except OSError as exc:
            raise DeviceError(str(exc)) from exc
        if actual != enabled:
            raise DeviceError("Windows did not confirm the requested read-only state.")
        return actual
