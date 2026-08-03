from __future__ import annotations

import struct
import unittest

from app import gim, gim_patch


class GimPatchTests(unittest.TestCase):
    def test_patches_only_the_decide_label_pixels(self):
        source = bytes([0xAA]) * 0xFB38
        patched = gim_patch.patch_decide_labels(source)

        changed_ranges: set[int] = set()
        for offset, width, height, _labels in gim_patch.DECIDE_LABEL_IMAGES:
            size = width * height // 2
            self.assertNotEqual(patched[offset:offset + size], source[offset:offset + size])
            changed_ranges.update(range(offset, offset + size))

        self.assertEqual(len(patched), len(source))
        self.assertTrue(all(a == b for index, (a, b) in enumerate(zip(source, patched)) if index not in changed_ranges))

    def test_p4_swizzle_keeps_low_nibble_first(self):
        rows = tuple(
            ''.join(format((x + y) & 0x0F, 'x') for x in range(32))
            for y in range(8)
        )
        packed = gim.encode_p4_swizzled(rows)

        self.assertEqual(packed[0], 0x10)
        self.assertEqual(packed[1], 0x32)
        self.assertEqual(len(packed), 32 * 8 // 2)

    def test_loading_titles_change_only_picture_pixels(self):
        source = bytearray(0x10880)
        for index in range(30):
            self._write_palette(source, 0x8D0 + index * 0x8D0)

        patched = gim_patch.patch_loading_titles(bytes(source))
        changed = {
            position
            for index in range(30)
            for position in range(0x80 + index * 0x8D0, 0x880 + index * 0x8D0)
        }

        self.assertEqual(len(patched), len(source))
        self.assertTrue(any(patched[position] for position in changed))
        self.assertTrue(all(
            before == after
            for position, (before, after) in enumerate(zip(source, patched))
            if position not in changed
        ))

    def test_battle_briefing_changes_only_label_pixels(self):
        source = bytearray(0x36CC)
        self._write_palette(source, 0x2DEC)
        self._write_palette(source, 0x30DC)

        patched = gim_patch.patch_battle_briefing_labels(bytes(source))
        changed = set(range(0x259C, 0x2D9C)) | set(range(0x2E8C, 0x308C))

        self.assertEqual(len(patched), len(source))
        self.assertTrue(any(patched[position] for position in changed))
        self.assertTrue(all(
            before == after
            for position, (before, after) in enumerate(zip(source, patched))
            if position not in changed
        ))

    def test_splits_multi_picture_gim(self):
        header = b"MIG.00.1PSP\0\0\0\0\0"
        pictures = (
            struct.pack("<HHIII", 3, 0, 16, 16, 16),
            struct.pack("<HHIII", 3, 0, 16, 16, 16),
        )
        root = struct.pack("<HHIII", 2, 0, 48, 16, 16)

        split = gim.split_gim_pictures(header + root + b"".join(pictures))

        self.assertEqual(len(split), 2)
        self.assertTrue(all(len(picture) == 48 for picture in split))

    @staticmethod
    def _write_palette(data, offset):
        for index in range(16):
            data[offset + index * 2:offset + index * 2 + 2] = (
                ((index << 12) | 0x09E).to_bytes(2, "little")
            )


if __name__ == '__main__':
    unittest.main()
