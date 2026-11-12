"""USB SECURITY launcher.

Kept at the original path so shortcuts, the PyInstaller spec and the README commands still work.
All code lives in the `usb_security` package.

    python USB_Security.py            # Windows, real drives
"""
import sys

from usb_security.app import main

if __name__ == "__main__":
    sys.exit(main())
