#!/usr/bin/env python3
"""List likely CP932 strings from an ELF32 EBOOT .rodata section."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


ELF_HEADER = struct.Struct("<16sHHIIIIIHHHHHH")
SECTION_HEADER = struct.Struct("<IIIIIIIIII")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("eboot", type=Path)
    parser.add_argument("--min-visible", type=int, default=4)
    parser.add_argument("--include-short", action="store_true")
    args = parser.parse_args()
    data = args.eboot.read_bytes()
    address, start, size = rodata_section(data)
    for offset, text in scan(data, start, size, args.min_visible, args.include_short):
        section_address = address + offset - start
        print(f"0x{offset:08X}\t0x{section_address:08X}\t{text!r}")
    return 0


def rodata_section(data: bytes) -> tuple[int, int, int]:
    if len(data) < ELF_HEADER.size:
        raise ValueError("file is smaller than its ELF header")
    header = ELF_HEADER.unpack_from(data)
    ident, machine = header[0], header[2]
    section_offset, entry_size, count, string_index = header[6], header[11], header[12], header[13]
    if ident[:6] != b"\x7fELF\x01\x01" or machine != 8:
        raise ValueError("expected a little-endian MIPS ELF32 file")
    if entry_size < SECTION_HEADER.size or string_index >= count:
        raise ValueError("invalid ELF section table")
    sections = [
        SECTION_HEADER.unpack_from(data, section_offset + index * entry_size)
        for index in range(count)
    ]
    names_header = sections[string_index]
    names = data[names_header[4] : names_header[4] + names_header[5]]
    for section in sections:
        name_end = names.find(b"\0", section[0])
        name = names[section[0] : name_end].decode("ascii")
        if name == ".rodata":
            return section[3], section[4], section[5]
    raise ValueError("ELF has no .rodata section")


def scan(
    data: bytes,
    start: int,
    size: int,
    min_visible: int,
    include_short: bool,
):
    position = start
    limit = start + size
    while position < limit:
        end = data.find(b"\0", position, limit)
        if end < 0:
            break
        raw = data[position:end]
        text = candidate(raw, min_visible, include_short)
        if text is not None:
            yield position, text
        position = end + 1


def candidate(raw: bytes, min_visible: int, include_short: bool) -> str | None:
    if len(raw) < 4 or not plausible_cp932(raw):
        return None
    try:
        text = raw.decode("cp932")
    except UnicodeDecodeError:
        return None
    try:
        utf8 = raw.decode("utf-8")
    except UnicodeDecodeError:
        utf8 = ""
    if utf8 != text and sum(is_japanese(char) for char in utf8) >= 2:
        return None
    visible = [char for char in text if not char.isspace()]
    japanese = sum(is_japanese(char) for char in visible)
    if len(visible) >= min_visible and japanese >= 2:
        return text
    if include_short and len(visible) >= 2 and japanese == len(visible):
        return text
    return None


def plausible_cp932(raw: bytes) -> bool:
    position = 0
    while position < len(raw):
        byte = raw[position]
        if byte in {9, 10, 13} or 0x20 <= byte <= 0x7E or 0xA1 <= byte <= 0xDF:
            position += 1
        elif (0x81 <= byte <= 0x9F or 0xE0 <= byte <= 0xFC) and position + 1 < len(raw):
            trail = raw[position + 1]
            if not (0x40 <= trail <= 0xFC and trail != 0x7F):
                return False
            position += 2
        else:
            return False
    return True


def is_japanese(char: str) -> bool:
    return (
        "\u3040" <= char <= "\u30FF"
        or "\u3400" <= char <= "\u9FFF"
        or "\uFF01" <= char <= "\uFF60"
        or char in "、。『』「」【】〜ー…"
    )


if __name__ == "__main__":
    raise SystemExit(main())
