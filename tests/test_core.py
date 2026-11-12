import ctypes
import hashlib
import tempfile
import threading
import unittest
from pathlib import Path

from usb_security.core.errors import ManifestError, ScanCancelled, ScanIncompleteError
from usb_security.core.manifest import diff, manifests_match, read_manifest, write_manifest
from usb_security.core.models import ChangeType, DriveInfo, FileEntry
from usb_security.core.references import ReferenceStore
from usb_security.core.scanner import scan_files
from usb_security.core.service import IntegrityService
from usb_security.core.utils import ellipsize_middle, human_duration, human_size


def make_tree(root: Path):
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "a.txt").write_bytes(b"alpha")
    (root / "b.bin").write_bytes(b"\x00" * 10)
    # all of these must be ignored at the root
    for name in (".USBIntegrity", "USB_Protection", "System Volume Information", "$RECYCLE.BIN"):
        (root / name).mkdir()
        (root / name / "ignored.txt").write_text("x")


def drive_for(root: Path, serial="TEST0001") -> DriveInfo:
    return DriveInfo("T", str(root), "TEST", "FAT32", serial, 1000, 500, 7)


class ScannerTests(unittest.TestCase):
    def test_hashes_and_exclusions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); make_tree(root)
            result = scan_files(root)
            self.assertEqual([e.path for e in result.entries], ["b.bin", "docs/a.txt"])
            alpha = next(e for e in result.entries if e.path == "docs/a.txt")
            self.assertEqual(alpha.sha256, hashlib.sha256(b"alpha").hexdigest())
            self.assertEqual(alpha.length, 5)
            self.assertEqual(result.total_bytes, 15)
            self.assertFalse(result.errors)

    def test_nested_folder_with_excluded_name_is_still_scanned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "sub" / ".USBIntegrity").mkdir(parents=True)
            (root / "sub" / ".USBIntegrity" / "x.txt").write_text("hi")
            self.assertEqual([e.path for e in scan_files(root).entries], ["sub/.USBIntegrity/x.txt"])

    def test_cancel(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); make_tree(root)
            event = threading.Event(); event.set()
            with self.assertRaises(ScanCancelled):
                scan_files(root, cancel=event)

    def test_progress_reaches_100_percent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); make_tree(root)
            seen = []
            scan_files(root, progress=seen.append)
            self.assertEqual(seen[0].phase, "enumerate")
            self.assertEqual(seen[-1].fraction, 1.0)
            self.assertEqual(seen[-1].files_done, 2)


class ManifestTests(unittest.TestCase):
    def test_round_trip_and_v1_compatibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m" / "integrity.csv"
            entries = [FileEntry("a.txt", 5, "ab" * 32), FileEntry("d/é.txt", 0, "cd" * 32)]
            write_manifest(path, entries)
            self.assertEqual(read_manifest(path), entries)
            self.assertFalse(list(path.parent.glob("*.tmp")))
            # a file written by v1 (utf-8-sig, same header) must load
            path.write_text("RelativePath,Length,SHA256\r\nx.txt,3," + "EF" * 32 + "\r\n", encoding="utf-8-sig")
            self.assertEqual(read_manifest(path)[0].sha256, "ef" * 32)

    def test_invalid_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.csv"
            bad.write_text("Foo,Bar\n1,2\n"); self.assertRaises(ManifestError, read_manifest, bad)
            bad.write_text(""); self.assertRaises(ManifestError, read_manifest, bad)
            bad.write_text("RelativePath,Length,SHA256\nx,notanumber,aa\n")
            self.assertRaises(ManifestError, read_manifest, bad)
            self.assertRaises(ManifestError, read_manifest, Path(tmp) / "missing.csv")

    def test_diff_kinds(self):
        old = [FileEntry("keep.txt", 1, "a"), FileEntry("mod.txt", 1, "b"), FileEntry("gone.txt", 1, "c")]
        new = [FileEntry("KEEP.txt", 1, "a"), FileEntry("mod.txt", 2, "z"), FileEntry("new.txt", 4, "d")]
        kinds = {(c.kind, c.path) for c in diff(old, new)}
        self.assertEqual(kinds, {(ChangeType.MODIFIED, "mod.txt"), (ChangeType.DELETED, "gone.txt"),
                                 (ChangeType.ADDED, "new.txt")})
        self.assertTrue(manifests_match(old[:1], new[:1]))  # case-insensitive paths


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "usb"; self.root.mkdir(); make_tree(self.root)
        self.service = IntegrityService(ReferenceStore(Path(self.tmp.name) / "pc"))
        self.drive = drive_for(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_verify_without_references_fails(self):
        report = self.service.verify(self.drive)
        self.assertFalse(report.passed)
        self.assertFalse(report.scanned)
        self.assertEqual(len(report.failure_reasons()), 2)

    def test_create_then_verify_passes_then_detects_tampering(self):
        result = self.service.create(self.drive)
        self.assertEqual(result.file_count, 2)
        status = self.service.reference_status(self.drive)
        self.assertTrue(status.pc_found and status.usb_found)
        self.assertTrue(self.service.verify(self.drive).passed)

        (self.root / "docs" / "a.txt").write_bytes(b"ALPHA!")     # modified
        (self.root / "new.exe").write_bytes(b"MZ")                # added
        (self.root / "b.bin").unlink()                            # deleted
        report = self.service.verify(self.drive)
        self.assertFalse(report.passed)
        self.assertEqual((report.count(ChangeType.ADDED), report.count(ChangeType.MODIFIED),
                          report.count(ChangeType.DELETED)), (1, 1, 1))
        self.assertEqual(report.baseline, "LOCAL_PC")

    def test_pc_and_usb_reference_mismatch_is_detected(self):
        self.service.create(self.drive)
        pc = Path(self.service.store.pc_path(self.drive.serial))
        entries = read_manifest(pc)
        write_manifest(pc, entries[:-1])               # someone edited the PC copy
        report = self.service.verify(self.drive)
        self.assertIs(report.refs_match, False)
        self.assertFalse(report.passed)

    def test_only_usb_reference_never_passes(self):
        self.service.create(self.drive)
        Path(self.service.store.pc_path(self.drive.serial)).unlink()
        report = self.service.verify(self.drive)
        self.assertEqual(report.baseline, "SAVED_USB")
        self.assertFalse(report.passed)

    def test_create_refuses_incomplete_scan(self):
        class FakeScan:
            entries, errors, total_bytes = [], ["Cannot read 'x': denied"], 0
        service = IntegrityService(self.service.store, scanner=lambda *a, **k: FakeScan())
        with self.assertRaises(ScanIncompleteError):
            service.create(self.drive)
        self.assertFalse(self.service.reference_status(self.drive).pc_found)

    def test_unreadable_files_fail_verification(self):
        self.service.create(self.drive)

        class FakeScan:
            entries = scan_files(self.root).entries
            errors = ["Cannot read 'secret.txt': denied"]
            total_bytes = 0
        service = IntegrityService(self.service.store, scanner=lambda *a, **k: FakeScan())
        self.assertFalse(service.verify(self.drive).passed)


class UtilTests(unittest.TestCase):
    def test_formatters(self):
        self.assertEqual(human_size(0), "0 B")
        self.assertEqual(human_size(1536), "1.5 KB")
        self.assertEqual(human_duration(75), "1m 15s")
        self.assertEqual(len(ellipsize_middle("x" * 300, 50)), 50)


@unittest.skipUnless(ctypes.sizeof(ctypes.c_void_p) == 8, "layout checks assume 64-bit")
class WinApiLayoutTests(unittest.TestCase):
    """The v1 structs had the wrong sizes; lock the real Windows SDK layouts in."""

    def test_struct_layouts(self):
        from usb_security.device import winapi as w
        self.assertEqual(ctypes.sizeof(w.GET_DISK_ATTRIBUTES), 16)
        self.assertEqual(ctypes.sizeof(w.SET_DISK_ATTRIBUTES), 40)
        self.assertEqual(ctypes.sizeof(w.DISK_EXTENT), 24)
        self.assertEqual(w.VOLUME_DISK_EXTENTS.Extents.offset, 8)
        self.assertEqual(ctypes.sizeof(w.STORAGE_PROPERTY_QUERY), 12)
        self.assertEqual(w.STORAGE_DEVICE_DESCRIPTOR_HEADER.BusType.offset, 28)

    def test_device_paths(self):
        from usb_security.device import winapi as w
        self.assertEqual(w.volume_path("E:\\"), "\\\\.\\E:")
        self.assertEqual(w.physical_drive_path(3), "\\\\.\\PhysicalDrive3")


if __name__ == "__main__":
    unittest.main()
