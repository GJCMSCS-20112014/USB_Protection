"""Guards the layering that keeps the project scalable and testable."""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ArchitectureTests(unittest.TestCase):
    def test_logic_layers_never_import_tkinter(self):
        code = ("import sys, usb_security.core.service, "
                "usb_security.device.base, usb_security.ui.controller, usb_security.app; "
                "sys.exit(1 if 'tkinter' in sys.modules else 0)")
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT)
        self.assertEqual(result.returncode, 0, "core/device/controller must stay free of tkinter")

    def test_windows_layer_imports_on_any_os(self):
        code = "import usb_security.device.winapi, usb_security.device.windows"
        self.assertEqual(subprocess.run([sys.executable, "-c", code], cwd=ROOT).returncode, 0)


if __name__ == "__main__":
    unittest.main()
