"""Windows USB device backend factory."""
from __future__ import annotations

from .base import DeviceBackend


def create_backend() -> DeviceBackend:
    """Create the real Windows hardware backend."""
    from .windows import WindowsBackend
    return WindowsBackend()
