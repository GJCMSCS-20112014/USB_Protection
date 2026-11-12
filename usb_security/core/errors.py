"""Exception hierarchy. The UI catches UsbSecurityError for friendly messages."""
from __future__ import annotations


class UsbSecurityError(Exception):
    """Base class for all expected application errors."""


class ManifestError(UsbSecurityError):
    """An integrity reference file is missing columns or contains invalid data."""


class ScanCancelled(UsbSecurityError):
    """The user cancelled a running scan."""


class ScanIncompleteError(UsbSecurityError):
    """Some files or folders could not be read, so the result would not be trustworthy."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__(f"{len(self.errors)} item(s) could not be read.")


class DeviceError(UsbSecurityError):
    """A device / disk operation failed."""


class BlockedError(DeviceError):
    """A safety rule refused the operation (system disk, non-USB bus, multi-disk volume...)."""


class AdminRequiredError(DeviceError):
    """The operation needs Administrator rights."""
