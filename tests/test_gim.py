from __future__ import annotations

import unittest

from app import gim, gim_patch


class GimPatchTests(unittest.TestCase):
    def test_patches_only_the_decide_label_pixels(self):
        source = bytes([0xAA]) * 0xFB38
        patched = gim_patch.patch_decide_labels(source)

        changed_ranges: set[int] = set()
        for offset, rows in gim_patch.DECIDE_LABEL_MASKS:
            encoded = gim.encode_p4_swizzled(rows)
            self.assertEqual(patched[offset:offset + len(encoded)], encoded)
            changed_ranges.update(range(offset, offset + len(encoded)))

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


if __name__ == '__main__':
    unittest.main()
