"""Thin ctypes wrappers around the Win32 storage APIs.

Importable on any OS (structures only); the kernel32 handle is created lazily so unit tests
can check struct layouts on Linux. Every function here talks to Windows and may raise WinApiError.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from ctypes import wintypes
from dataclasses import dataclass
from typing import List, Optional, Tuple

DRIVE_REMOVABLE = 2
DRIVE_FIXED = 3
OPEN_EXISTING = 3
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
ERROR_MORE_DATA = 234

IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS = 0x00560000
IOCTL_STORAGE_QUERY_PROPERTY = 0x002D1400
IOCTL_DISK_GET_DISK_ATTRIBUTES = 0x000700F0
IOCTL_DISK_SET_DISK_ATTRIBUTES = 0x0007C0F4
STORAGE_DEVICE_PROPERTY = 0
PROPERTY_STANDARD_QUERY = 0
DISK_ATTRIBUTE_READ_ONLY = 0x0000000000000002
MAX_EXTENTS = 16
U32 = ctypes.c_uint32  # fixed width: wintypes.DWORD is 8 bytes on LP64 Linux, 4 on Windows


class DISK_EXTENT(ctypes.Structure):
    _fields_ = [("DiskNumber", U32),
                ("StartingOffset", ctypes.c_longlong),
                ("ExtentLength", ctypes.c_longlong)]


class VOLUME_DISK_EXTENTS(ctypes.Structure):
    _fields_ = [("NumberOfDiskExtents", U32),
                ("Extents", DISK_EXTENT * MAX_EXTENTS)]


class STORAGE_PROPERTY_QUERY(ctypes.Structure):
    _fields_ = [("PropertyId", U32),
                ("QueryType", U32),
                ("AdditionalParameters", ctypes.c_ubyte * 1)]


class STORAGE_DEVICE_DESCRIPTOR_HEADER(ctypes.Structure):
    _fields_ = [("Version", U32), ("Size", U32),
                ("DeviceType", ctypes.c_ubyte), ("DeviceTypeModifier", ctypes.c_ubyte),
                ("RemovableMedia", ctypes.c_ubyte), ("CommandQueueing", ctypes.c_ubyte),
                ("VendorIdOffset", U32), ("ProductIdOffset", U32),
                ("ProductRevisionOffset", U32), ("SerialNumberOffset", U32),
                ("BusType", U32), ("RawPropertiesLength", U32)]


class GET_DISK_ATTRIBUTES(ctypes.Structure):
    # Real layout is 16 bytes: v1 wrongly appended an AttributesMask field.
    _fields_ = [("Version", U32),
                ("Reserved1", U32),
                ("Attributes", ctypes.c_ulonglong)]


class SET_DISK_ATTRIBUTES(ctypes.Structure):
    # Real layout is 40 bytes; v1 omitted Reserved2, so Version/size did not match what Windows expects.
    _fields_ = [("Version", U32),
                ("Persist", ctypes.c_ubyte),
                ("RelinquishOwnership", ctypes.c_ubyte),
                ("Reserved1", ctypes.c_ubyte * 2),
                ("Attributes", ctypes.c_ulonglong),
                ("AttributesMask", ctypes.c_ulonglong),
                ("Reserved2", U32 * 4)]


class WinApiError(OSError):
    def __init__(self, message: str, code: int = 0):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DiskDescriptor:
    bus_type: int
    vendor: str
    product: str
    serial: str


_kernel32 = None


def _k32():
    """Create kernel32 with explicit prototypes (v1 used default int restype, which truncates
    64-bit handles and made the INVALID_HANDLE_VALUE check unreliable)."""
    global _kernel32
    if _kernel32 is None:
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                  wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        k.CreateFileW.restype = wintypes.HANDLE
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.CloseHandle.restype = wintypes.BOOL
        k.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                                      wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                      wintypes.LPVOID]
        k.DeviceIoControl.restype = wintypes.BOOL
        k.GetLogicalDrives.restype = wintypes.DWORD
        k.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
        k.GetDriveTypeW.restype = wintypes.UINT
        k.GetVolumeInformationW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
                                            ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
                                            ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.DWORD]
        k.GetVolumeInformationW.restype = wintypes.BOOL
        _kernel32 = k
    return _kernel32


def _raise(prefix: str):
    code = ctypes.get_last_error()
    raise WinApiError(f"{prefix}: {ctypes.FormatError(code).strip()} (error {code})", code)


def volume_path(root: str) -> str:
    return r"\\.\{}".format(root.rstrip("\\"))      # E:\ -> \\.\E:   (v1 produced \\.\\E:)


def physical_drive_path(number: int) -> str:
    return rf"\\.\PhysicalDrive{number}"


class DeviceHandle:
    """CreateFile/CloseHandle as a context manager. access=0 queries without needing admin."""

    def __init__(self, path: str, access: int = 0, share: int = FILE_SHARE_READ | FILE_SHARE_WRITE):
        handle = _k32().CreateFileW(path, access, share, None, OPEN_EXISTING, 0, None)
        if handle in (None, INVALID_HANDLE_VALUE):
            _raise(f"Cannot open {path}")
        self._handle = handle

    def __enter__(self) -> "DeviceHandle":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._handle:
            _k32().CloseHandle(self._handle)
            self._handle = None

    def ioctl(self, code: int, in_buf=None, out_buf=None) -> int:
        returned = wintypes.DWORD()
        ok = _k32().DeviceIoControl(
            self._handle, code,
            ctypes.byref(in_buf) if in_buf is not None else None,
            ctypes.sizeof(in_buf) if in_buf is not None else 0,
            ctypes.byref(out_buf) if out_buf is not None else None,
            ctypes.sizeof(out_buf) if out_buf is not None else 0,
            ctypes.byref(returned), None)
        if not ok:
            _raise(f"DeviceIoControl 0x{code:08X} failed")
        return returned.value


def volume_disk_numbers(root: str) -> List[int]:
    with DeviceHandle(volume_path(root)) as handle:
        extents = VOLUME_DISK_EXTENTS()
        try:
            handle.ioctl(IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS, out_buf=extents)
        except WinApiError as exc:
            if exc.code != ERROR_MORE_DATA:
                raise
        count = min(extents.NumberOfDiskExtents, MAX_EXTENTS)
        return [extents.Extents[i].DiskNumber for i in range(count)]


def _cstr(raw: bytes, offset: int) -> str:
    if not offset or offset >= len(raw):
        return ""
    end = raw.find(b"\0", offset)
    return raw[offset:len(raw) if end < 0 else end].decode("ascii", "replace").strip()


def query_disk_descriptor(number: int) -> DiskDescriptor:
    with DeviceHandle(physical_drive_path(number)) as handle:
        query = STORAGE_PROPERTY_QUERY()
        query.PropertyId = STORAGE_DEVICE_PROPERTY
        query.QueryType = PROPERTY_STANDARD_QUERY
        buffer = ctypes.create_string_buffer(4096)
        returned = wintypes.DWORD()
        ok = _k32().DeviceIoControl(handle._handle, IOCTL_STORAGE_QUERY_PROPERTY,
                                    ctypes.byref(query), ctypes.sizeof(query),
                                    buffer, ctypes.sizeof(buffer), ctypes.byref(returned), None)
        if not ok:
            _raise("Cannot query physical disk information")
        raw = buffer.raw[:returned.value]
        header = STORAGE_DEVICE_DESCRIPTOR_HEADER.from_buffer_copy(raw[:ctypes.sizeof(STORAGE_DEVICE_DESCRIPTOR_HEADER)])
        return DiskDescriptor(header.BusType, _cstr(raw, header.VendorIdOffset),
                              _cstr(raw, header.ProductIdOffset), _cstr(raw, header.SerialNumberOffset))


def get_read_only(number: int) -> bool:
    with DeviceHandle(physical_drive_path(number)) as handle:
        data = GET_DISK_ATTRIBUTES()
        handle.ioctl(IOCTL_DISK_GET_DISK_ATTRIBUTES, out_buf=data)
        return bool(data.Attributes & DISK_ATTRIBUTE_READ_ONLY)


def set_read_only(number: int, enabled: bool) -> bool:
    """Set the persistent read-only attribute and return the state Windows reports afterwards."""
    with DeviceHandle(physical_drive_path(number), GENERIC_READ | GENERIC_WRITE) as handle:
        data = SET_DISK_ATTRIBUTES()
        data.Version = ctypes.sizeof(data)
        data.Persist = 1
        data.RelinquishOwnership = 0
        data.Attributes = DISK_ATTRIBUTE_READ_ONLY if enabled else 0
        data.AttributesMask = DISK_ATTRIBUTE_READ_ONLY
        handle.ioctl(IOCTL_DISK_SET_DISK_ATTRIBUTES, in_buf=data)
    return get_read_only(number)


def list_logical_drives() -> List[Tuple[str, str, int]]:
    """[(letter, root, drive_type)] for fixed and removable drives."""
    k = _k32()
    mask = k.GetLogicalDrives()
    result = []
    for index in range(26):
        if mask & (1 << index):
            letter = chr(65 + index)
            root = f"{letter}:\\"
            dtype = k.GetDriveTypeW(root)
            if dtype in (DRIVE_REMOVABLE, DRIVE_FIXED):
                result.append((letter, root, dtype))
    return result


def volume_info(root: str) -> Tuple[str, str, str]:
    """(label, filesystem, serial-hex)."""
    serial = wintypes.DWORD()
    label = ctypes.create_unicode_buffer(261)
    fs = ctypes.create_unicode_buffer(64)
    _k32().GetVolumeInformationW(root, label, len(label), ctypes.byref(serial), None, None, fs, len(fs))
    return label.value, fs.value, f"{serial.value:08X}"


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> bool:
    """Re-run this program elevated (UAC prompt). Handles both `python script.py` and a frozen EXE
    (v1 passed the EXE path to itself as an extra argument when frozen)."""
    if getattr(sys, "frozen", False):
        args = sys.argv[1:]
    else:
        args = [os.path.abspath(sys.argv[0]), *sys.argv[1:]]
    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable,
                                                 subprocess.list2cmdline(args), None, 1)
    return result > 32
