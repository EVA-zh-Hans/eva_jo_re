from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from . import paratranz


class EbootPatchError(ValueError):
    pass


@dataclass(frozen=True)
class Entry:
    key: str
    offset: int
    original: str
    translation: str
    context: str


@dataclass(frozen=True)
class PatchSet:
    data: bytes
    entries: tuple[Entry, ...]

    @property
    def original_texts(self) -> tuple[str, ...]:
        return tuple(entry.original for entry in self.entries)

    @property
    def translated_texts(self) -> tuple[str, ...]:
        return tuple(entry.translation for entry in self.entries)


def load_entries(path: Path) -> tuple[Entry, ...]:
    raw_entries = paratranz.load(path)
    entries: list[Entry] = []
    offsets: set[int] = set()
    for index, raw in enumerate(raw_entries):
        raw_offset = raw.get("offset")
        context = raw.get("context")
        try:
            offset = (
                int(raw_offset, 16)
                if isinstance(raw_offset, str) and raw_offset.startswith("0x")
                else raw_offset
            )
        except ValueError:
            offset = None
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise EbootPatchError(f"Entry {index} has invalid offset: {path}")
        if not isinstance(context, str):
            raise EbootPatchError(f"Entry {index} has invalid context: {path}")
        expected_key = f"eboot_{offset:08x}"
        if raw["key"] != expected_key:
            raise EbootPatchError(
                f"Entry {index} key must be {expected_key!r}, got {raw['key']!r}"
            )
        if offset in offsets:
            raise EbootPatchError(f"Duplicate EBOOT offset 0x{offset:08X}: {path}")
        offsets.add(offset)
        translation = raw["translation"].replace("\r\n", "\n").replace("\r", "\n")
        if not translation:
            raise EbootPatchError(f"Entry {expected_key} has an empty translation")
        if translation == raw["original"]:
            raise EbootPatchError(f"Entry {expected_key} is a no-op translation")
        if "\0" in translation:
            raise EbootPatchError(f"Entry {expected_key} contains NUL")
        _validate_controls(expected_key, raw["original"], translation)
        entries.append(
            Entry(
                key=expected_key,
                offset=offset,
                original=raw["original"],
                translation=translation,
                context=context,
            )
        )
    return tuple(entries)


def load(source: bytes, path: Path) -> PatchSet:
    entries = load_entries(path)
    for entry in entries:
        original = entry.original.encode("cp932", errors="strict")
        end = entry.offset + len(original)
        if end >= len(source):
            raise EbootPatchError(f"Entry {entry.key} is outside the EBOOT")
        if source[entry.offset:end] != original or source[end] != 0:
            raise EbootPatchError(
                f"Entry {entry.key} does not match the source EBOOT at "
                f"0x{entry.offset:08X}"
            )
    return PatchSet(source, entries)


def replace(
    patch_set: PatchSet,
    substitutions: Mapping[str, str] | None = None,
) -> bytes:
    output = bytearray(patch_set.data)
    for entry in patch_set.entries:
        original = entry.original.encode("cp932", errors="strict")
        encoded_text = (
            "".join(substitutions.get(char, char) for char in entry.translation)
            if substitutions
            else entry.translation
        )
        try:
            encoded = encoded_text.encode("cp932", errors="strict")
        except UnicodeEncodeError as exc:
            char = encoded_text[exc.start : exc.end]
            raise EbootPatchError(f"Cannot encode {char!r} for {entry.key}") from exc
        if len(encoded) > len(original):
            raise EbootPatchError(
                f"Entry {entry.key} needs {len(encoded)} bytes, but its in-place "
                f"slot has {len(original)}"
            )
        start = entry.offset
        output[start : start + len(original)] = encoded.ljust(len(original), b"\0")
    return bytes(output)


def verify_patched(data: bytes, entries: tuple[Entry, ...]) -> list[str]:
    errors: list[str] = []
    for entry in entries:
        original = entry.original.encode("cp932", errors="strict")
        end = entry.offset + len(original)
        if end > len(data):
            errors.append(f"Patched EBOOT entry is out of range: {entry.key}")
        elif data[entry.offset:end] == original:
            errors.append(f"EBOOT entry was not translated: {entry.key}")
    return errors


def _validate_controls(key: str, original: str, translation: str) -> None:
    source_controls = [
        value
        for value in paratranz.CONTROL.findall(original)
        if value not in paratranz.LAYOUT_CONTROLS
    ]
    translated_controls = [
        value
        for value in paratranz.CONTROL.findall(translation)
        if value not in paratranz.LAYOUT_CONTROLS
    ]
    if Counter(source_controls) != Counter(translated_controls):
        raise EbootPatchError(
            f"Control sequence mismatch for {key}: "
            f"{source_controls!r} != {translated_controls!r}"
        )
