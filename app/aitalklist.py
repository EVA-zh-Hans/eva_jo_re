from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .encoding import EncodingError, encode_game_text


RECORD_SIZE = 0x70
TEXT_SIZE = 0x20
CHARACTER_OFFSET = 0x20
CHARACTER_SIZE = 0x20
SENTINEL = bytes([0xFF]) * RECORD_SIZE


class AiTalkListError(ValueError):
    pass


@dataclass(frozen=True)
class StringField:
    ordinal: int
    row: int
    original: str
    character: str


@dataclass(frozen=True)
class TextSpan:
    ordinal: int
    original: str
    context: str


@dataclass(frozen=True)
class Table:
    data: bytes
    strings: tuple[StringField, ...]


def parse(data: bytes) -> Table:
    if len(data) < RECORD_SIZE * 2 or len(data) % RECORD_SIZE:
        raise AiTalkListError(
            f"AI talk list size is not a multiple of 0x{RECORD_SIZE:X}: {len(data)}"
        )
    if data[-RECORD_SIZE:] != SENTINEL:
        raise AiTalkListError("AI talk list does not end with its 0xFF sentinel record")

    strings: list[StringField] = []
    for row in range(len(data) // RECORD_SIZE - 1):
        start = row * RECORD_SIZE
        original = _decode_slot(data[start : start + TEXT_SIZE], row, "text")
        character = _decode_slot(
            data[
                start + CHARACTER_OFFSET : start + CHARACTER_OFFSET + CHARACTER_SIZE
            ],
            row,
            "character ID",
        )
        if not original:
            raise AiTalkListError(f"AI talk list row {row} has empty text")
        strings.append(StringField(row + 1, row, original, character))
    return Table(data, tuple(strings))


def scan(table: Table) -> list[TextSpan]:
    spans: list[TextSpan] = []
    for field in table.strings:
        if not any(ord(char) > 0x7F for char in field.original):
            continue
        character = field.character or "common"
        spans.append(
            TextSpan(
                field.ordinal,
                field.original,
                f"Row: {field.row}\nCharacter ID: {character}",
            )
        )
    return spans


def render(
    table: Table,
    spans: list[TextSpan],
    translations: Mapping[int, str],
) -> tuple[str, ...]:
    translatable = {span.ordinal for span in spans}
    rendered: list[str] = []
    for field in table.strings:
        translation = translations.get(field.ordinal, "") if field.ordinal in translatable else ""
        if not translation or translation == field.original:
            rendered.append(field.original)
            continue
        if "\0" in translation:
            raise AiTalkListError(f"Translation for row {field.row} contains NUL")
        rendered.append(translation.replace("\r\n", "\n").replace("\r", "\n"))
    return tuple(rendered)


def replace(
    table: Table,
    rendered: tuple[str, ...],
    substitutions: Mapping[str, str] | None = None,
) -> bytes:
    if len(rendered) != len(table.strings):
        raise AiTalkListError(
            f"Expected {len(table.strings)} rendered strings, got {len(rendered)}"
        )
    if all(
        text == field.original
        for field, text in zip(table.strings, rendered, strict=True)
    ):
        return table.data

    output = bytearray(table.data)
    for field, text in zip(table.strings, rendered, strict=True):
        try:
            encoded = encode_game_text(text, substitutions)
        except EncodingError as exc:
            raise AiTalkListError(
                f"Cannot encode text for row {field.row}: {exc}"
            ) from exc
        if len(encoded) >= TEXT_SIZE:
            raise AiTalkListError(
                f"Translation for row {field.row} needs {len(encoded)} bytes, "
                f"but its NUL-terminated slot allows {TEXT_SIZE - 1}"
            )
        start = field.row * RECORD_SIZE
        output[start : start + TEXT_SIZE] = encoded.ljust(TEXT_SIZE, b"\0")
    return bytes(output)


def _decode_slot(data: bytes, row: int, label: str) -> str:
    try:
        terminator = data.index(0)
    except ValueError as exc:
        raise AiTalkListError(
            f"AI talk list row {row} has unterminated {label}"
        ) from exc
    if any(data[terminator + 1 :]):
        raise AiTalkListError(f"AI talk list row {row} has dirty {label} padding")
    raw = data[:terminator]
    try:
        text = raw.decode("cp932", errors="strict")
    except UnicodeDecodeError as exc:
        raise AiTalkListError(
            f"AI talk list row {row} has invalid CP932 {label}"
        ) from exc
    if text.encode("cp932", errors="strict") != raw:
        raise AiTalkListError(
            f"AI talk list row {row} has non-round-trippable CP932 {label}"
        )
    return text
