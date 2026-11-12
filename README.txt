USB SECURITY 2.0 - INTEGRITY MANAGER (pure Python, Windows)

WHAT IT DOES
- Creates a SHA-256 reference of every file on a USB drive (one copy on the USB, one on this PC).
- Verifies the drive against both references and reports ADDED / MODIFIED / DELETED files.
- Locks the physical USB disk read-only (only after the integrity check passes) and unlocks it.
- Python standard library only. No BAT/PowerShell/DiskPart, no pip packages, no internet.

RUN
1. Install Python 3.9+ on Windows with Tcl/Tk support.
2. python USB_Security.py
3. Approve the Windows User Account Control (UAC) prompt. If you decline, the app exits.
4. Refresh devices, manually select the intended USB, then pick an action.

NEW IN 2.0
UI
- Fixed light theme (no theme switch), light Windows title bar, high-DPI aware.
- Device table with bus type, capacity bar, volume serial, lock state and reference status.
- Action tiles, live progress (files, bytes, speed, ETA) and a Cancel button. The window no
  longer freezes while hashing: all work runs on a background thread.
- Result banner (PASS/FAIL with reasons), Added/Modified/Deleted counters, separate Activity Log
  and Changes popup buttons, Copy log button, F5 to refresh.
- Typed LOCK / UNLOCK confirmation in a themed dialog.
Code
- Split into layers (see below) with unit tests; the v1 behaviour and CSV format are unchanged,
  so existing integrity references keep working.
Fixes found while refactoring (all in the Windows-API layer - please test on real hardware)
- Volume path was built as \\.\\E: instead of \\.\E:.
- SET_DISK_ATTRIBUTES was missing its Reserved2 field (struct was 24 bytes, Windows expects 40) and
  GET_DISK_ATTRIBUTES had an extra field (24 bytes, expected 16) - likely cause of lock/unlock errors.
- kernel32 calls had no argtypes/restype, so 64-bit handles were truncated and the invalid-handle
  check was unreliable.
- Unreadable files/folders now fail verification (v1 silently skipped unreadable folders) and
  Create refuses to save a reference with holes in it.
- Integrity references are written atomically (no half-written CSV if the USB is pulled).
- The application requests Administrator rights at startup through Windows UAC. If
  permission is declined or elevation fails, the application exits. The system disk is read
  from %SystemDrive% instead of a hard-coded C:.
- Change report CSV additionally lists previous/current SHA-256 (new columns at the end).

PROJECT LAYOUT
USB_Security.py            launcher (same path as v1)
usb_security/
  app.py                   composition root, command-line options
  config.py settings.py logging_setup.py
  core/                    pure logic, no Tk and no Windows APIs
    scanner.py             hashing with progress + cancel
    manifest.py            read / write / diff of integrity.csv
    service.py             create + verify use-cases
    models.py errors.py references.py reports.py utils.py
  device/                  real Windows USB hardware access
    base.py                DeviceBackend interface
    winapi.py windows.py   Win32 DeviceIoControl layer + safety rules
    ui/
    controller.py          workflows (confirmations, admin check, safety gates) - no Tk
    tasks.py               background worker + UI-thread callbacks
    main_window.py widgets.py theme.py dialogs.py   Tk views
tests/                     python -m unittest discover -s tests

EXTENDING
- New action: add an ActionSpec to ACTIONS in ui/controller.py and a method with the same name on
  Controller; a tile appears automatically.
- New platform/device type: implement DeviceBackend (device/base.py) and return it from
  device/__init__.py.
- New hash/report format: only core/ changes; the UI does not need to know.

TESTS
    python -m unittest discover -s tests
The core integrity logic and Windows struct layouts are covered by the retained unit tests.

BUILD EXE
The EXE must be built on Windows. PyInstaller must be installed beforehand (offline: use a
previously downloaded wheel).
    py -m pip install pyinstaller
    py -m PyInstaller USB_Security.spec
Output: dist\USB_Security.exe
(or: py -m PyInstaller --onefile --windowed --name USB_Security USB_Security.py)

DATA LOCATIONS
USB: <USB>:\.USBIntegrity\integrity.csv
PC:  Documents\USBProtection\Integrity\<volume-serial>.csv
Logs, change reports, settings: Documents\USBProtection\Logs and settings.json
(set USB_SECURITY_HOME to use a different folder)

SCAN EXCLUSIONS
Root-level .USBIntegrity, USB_Protection, System Volume Information and $RECYCLE.BIN are excluded.
Other hidden files are included. Empty folders are not tracked. A rename appears as DELETED + ADDED.

IMPORTANT SECURITY
- SHA-256 detects changes; it does not determine whether a file is malware.
- Create integrity references only after confirming the USB files are clean.
- Disk read-only is software-level protection, not a physical write blocker.
- Read-only affects the entire physical disk and may be cleared by privileged software.
- Read-only does not stop malware from being opened or executed.
- Keep a trusted backup of your PC integrity reference and important files.
- Lock/Unlock requires Administrator rights and Windows storage-driver support.
- The DeviceIoControl operations and the window itself were checked with unit tests and a stubbed
  UI, but have not been run on real Windows hardware by the author of this refactor. Test on your
  PC and a spare USB before relying on them.
