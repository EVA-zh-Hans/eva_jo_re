import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from app.pkg import (
    Archive,
    BDL_HEADER,
    BPK_HEADER,
    RAW_DIRECTORY,
    RAW_ENTRY,
    align_up,
    replace_entries,
)


def make_pkg(path: Path, payload: bytes, compressed: bool) -> None:
    stored = zlib.compress(payload) if compressed else payload
    data_offset = 0x800
    entry_offset = 0x1000
    name = b"TEST.NUT\0"
    directory_offset = align_up(entry_offset + RAW_ENTRY.size + len(name), 16)
    directory_name = b"DATA\0"
    total = directory_offset + RAW_DIRECTORY.size + align_up(len(directory_name), 4)
    output = bytearray(total)
    output[: BPK_HEADER.size] = BPK_HEADER.pack(
        b"BPK0", 0x25AC, directory_offset, directory_offset - entry_offset, entry_offset
    )
    output[data_offset : data_offset + BDL_HEADER.size] = BDL_HEADER.pack(
        b"BDL0", len(payload), len(stored) if compressed else 0, 7, 9, b"P" * 12
    )
    start = data_offset + BDL_HEADER.size
    output[start : start + len(stored)] = stored
    output[entry_offset : entry_offset + RAW_ENTRY.size] = RAW_ENTRY.pack(
        123, 0x800, len(payload), data_offset
    )
    output[entry_offset + RAW_ENTRY.size : entry_offset + RAW_ENTRY.size + len(name)] = name
    output[directory_offset : directory_offset + RAW_DIRECTORY.size] = RAW_DIRECTORY.pack(
        11, 22, 1, entry_offset, directory_offset - entry_offset, 0
    )
    output[directory_offset + RAW_DIRECTORY.size : directory_offset + RAW_DIRECTORY.size + len(directory_name)] = directory_name
    path.write_bytes(output)


class PkgTests(unittest.TestCase):
    def test_noop_is_byte_identical_and_fixed_layout_preserves_unknowns(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pkg"
            copy = root / "copy.pkg"
            patched = root / "patched.pkg"
            make_pkg(source, b"original", True)
            self.assertEqual(replace_entries(source, copy, {}), "copy")
            self.assertEqual(source.read_bytes(), copy.read_bytes())
            self.assertEqual(
                replace_entries(source, patched, {"DATA/TEST.NUT": b"translated"}),
                "fixed-layout",
            )
            with Archive(patched) as archive:
                entry = archive.get("DATA/TEST.NUT")
                self.assertEqual(archive.read(entry), b"translated")
                self.assertEqual(entry.bdl.unknown1, 7)
                self.assertEqual(entry.bdl.unknown2, 9)
                self.assertEqual(entry.bdl.padding, b"P" * 12)

    def test_growing_entry_falls_back_to_rebuild(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pkg"
            output = root / "output.pkg"
            make_pkg(source, b"small", False)
            replacement = b"x" * 3000
            self.assertEqual(
                replace_entries(source, output, {"DATA/TEST.NUT": replacement}), "rebuilt"
            )
            with Archive(output) as archive:
                self.assertEqual(archive.read("DATA/TEST.NUT"), replacement)


if __name__ == "__main__":
    unittest.main()
