"""Reading, writing and comparing integrity reference files (CSV, format unchanged from v1)."""
from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from ..config import MANIFEST_FIELDS
from .errors import ManifestError
from .models import Change, ChangeType, FileEntry


def read_manifest(path) -> List[FileEntry]:
    try:
        with open(path, newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or not set(MANIFEST_FIELDS).issubset(reader.fieldnames):
                raise ManifestError(f"Invalid integrity reference format: {path}")
            entries = []
            for line_no, row in enumerate(reader, start=2):
                try:
                    entries.append(FileEntry(row["RelativePath"], int(row["Length"]),
                                             str(row["SHA256"]).strip().lower()))
                except (TypeError, ValueError, KeyError) as exc:
                    raise ManifestError(f"Invalid row {line_no} in {path}") from exc
            return entries
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise ManifestError(f"Cannot read integrity reference {path}: {exc}") from exc


def write_manifest(path, entries: Iterable[FileEntry]) -> None:
    """Atomic write: a crash or unplugged USB never leaves a half-written reference."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    try:
        with temp.open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.writer(stream)
            writer.writerow(MANIFEST_FIELDS)
            for entry in entries:
                writer.writerow([entry.path, entry.length, entry.sha256])
        os.replace(temp, target)
    finally:
        if temp.exists():
            try:
                temp.unlink()
            except OSError:
                pass


def as_map(entries: Iterable[FileEntry]) -> Dict[str, Tuple[int, str]]:
    return {e.path.casefold(): (e.length, e.sha256.lower()) for e in entries}


def manifests_match(expected: Iterable[FileEntry], actual: Iterable[FileEntry]) -> bool:
    return as_map(expected) == as_map(actual)


def diff(expected: Iterable[FileEntry], actual: Iterable[FileEntry]) -> List[Change]:
    """ADDED / MODIFIED / DELETED relative to *expected*. A rename shows as DELETED + ADDED."""
    old = {e.path.casefold(): e for e in expected}
    new = {e.path.casefold(): e for e in actual}
    changes: List[Change] = []
    for key, entry in new.items():
        before = old.get(key)
        if before is None:
            changes.append(Change(ChangeType.ADDED, entry.path, None, entry.length, "", entry.sha256))
        elif before.length != entry.length or before.sha256 != entry.sha256:
            changes.append(Change(ChangeType.MODIFIED, entry.path, before.length, entry.length,
                                  before.sha256, entry.sha256))
    for key, entry in old.items():
        if key not in new:
            changes.append(Change(ChangeType.DELETED, entry.path, entry.length, None, entry.sha256, ""))
    return sorted(changes, key=lambda c: (c.kind.value, c.path.casefold()))
