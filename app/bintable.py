from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from typing import Mapping


HEADER = struct.Struct("<5I")
TYPE_WIDTHS = {0: 4, 1: 4, 2: 1, 3: 2, 4: 4}
STRING_TYPE = 4
NON_ASCII = re.compile(r"[^\x00-\x7f]")


class BinTableError(ValueError):
    pass


@dataclass(frozen=True)
class StringField:
    ordinal: int
    row: int
    column: int
    pointer_offset: int
    original: str


@dataclass(frozen=True)
class TextSpan:
    ordinal: int
    original: str
    context: str


@dataclass(frozen=True)
class Table:
    data: bytes
    record_offset: int
    record_count: int
    field_types: tuple[int, ...]
    record_size: int
    pool_offset: int
    strings: tuple[StringField, ...]


def parse(data: bytes) -> Table:
    if len(data) < HEADER.size:
        raise BinTableError("BIN table is smaller than its header")

    table_count, record_offset, record_count, field_count, field_types_offset = (
        HEADER.unpack_from(data)
    )
    if table_count != 1:
        raise BinTableError(f"Expected one BIN table, found: {table_count}")
    if field_types_offset != HEADER.size:
        raise BinTableError(
            f"Unexpected BIN field type offset: {field_types_offset}"
        )
    if field_count > 1024:
        raise BinTableError(f"Unreasonable BIN table field count: {field_count}")

    expected_record_offset = field_types_offset + field_count * 4
    if record_offset != expected_record_offset:
        raise BinTableError(
            f"Unexpected BIN table record offset: {record_offset} != {expected_record_offset}"
        )
    if record_offset > len(data):
        raise BinTableError("BIN table field descriptors exceed the file")

    field_types = struct.unpack_from(f"<{field_count}I", data, field_types_offset)
    unsupported = sorted(set(field_types) - TYPE_WIDTHS.keys())
    if unsupported:
        raise BinTableError(f"Unsupported BIN table field types: {unsupported}")

    field_offsets: list[int] = []
    record_size = 0
    for field_type in field_types:
        field_offsets.append(record_size)
        record_size += TYPE_WIDTHS[field_type]
    pool_offset = record_offset + record_count * record_size
    if pool_offset > len(data):
        raise BinTableError("BIN table records exceed the file")

    strings: list[StringField] = []
    ordinal = 0
    for row in range(record_count):
        row_offset = record_offset + row * record_size
        for column, (field_type, field_offset) in enumerate(zip(field_types, field_offsets)):
            if field_type != STRING_TYPE:
                continue
            ordinal += 1
            pointer_offset = row_offset + field_offset
            pointer = struct.unpack_from("<I", data, pointer_offset)[0]
            if not pool_offset <= pointer < len(data):
                raise BinTableError(
                    f"String pointer for row {row}, column {column} is out of range: 0x{pointer:X}"
                )
            terminator = data.find(b"\0", pointer)
            if terminator < 0:
                raise BinTableError(f"Unterminated string for row {row}, column {column}")
            raw = data[pointer:terminator]
            try:
                original = raw.decode("cp932", errors="strict")
            except UnicodeDecodeError as exc:
                raise BinTableError(
                    f"Invalid CP932 string for row {row}, column {column}"
                ) from exc
            if original.encode("cp932", errors="strict") != raw:
                raise BinTableError(
                    f"Non-round-trippable CP932 string for row {row}, column {column}"
                )
            strings.append(StringField(ordinal, row, column, pointer_offset, original))

    _validate_pool(data, pool_offset, strings)
    return Table(
        data=data,
        record_offset=record_offset,
        record_count=record_count,
        field_types=tuple(field_types),
        record_size=record_size,
        pool_offset=pool_offset,
        strings=tuple(strings),
    )


def scan(table: Table, field_labels: Mapping[int, str]) -> list[TextSpan]:
    string_columns = {
        column for column, field_type in enumerate(table.field_types) if field_type == STRING_TYPE
    }
    if set(field_labels) != string_columns:
        raise BinTableError(
            f"BIN text field labels do not match string columns: "
            f"{sorted(field_labels)} != {sorted(string_columns)}"
        )

    spans: list[TextSpan] = []
    for field in table.strings:
        if not field.original.strip(" \t\r\n\u3000") or not NON_ASCII.search(field.original):
            continue
        label = field_labels[field.column]
        spans.append(
            TextSpan(
                ordinal=field.ordinal,
                original=field.original,
                context=f"Row: {field.row}\nField: {label} (column {field.column})",
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
            raise BinTableError(
                f"Translation for row {field.row}, column {field.column} contains NUL"
            )
        rendered.append(translation.replace("\r\n", "\n").replace("\r", "\n"))
    return tuple(rendered)


def replace(
    table: Table,
    rendered: tuple[str, ...],
    substitutions: Mapping[str, str] | None = None,
) -> bytes:
    if len(rendered) != len(table.strings):
        raise BinTableError(
            f"Expected {len(table.strings)} rendered strings, got {len(rendered)}"
        )
    if all(text == field.original for field, text in zip(table.strings, rendered, strict=True)):
        return table.data

    records = bytearray(table.data[: table.pool_offset])
    pool = bytearray()
    for field, text in zip(table.strings, rendered, strict=True):
        if "\0" in text:
            raise BinTableError(
                f"Rendered text for row {field.row}, column {field.column} contains NUL"
            )
        encoded_text = "".join(substitutions.get(char, char) for char in text) if substitutions else text
        try:
            encoded = encoded_text.encode("cp932", errors="strict")
        except UnicodeEncodeError as exc:
            char = encoded_text[exc.start : exc.end]
            raise BinTableError(
                f"Cannot encode {char!r} for row {field.row}, column {field.column}"
            ) from exc
        pointer = table.pool_offset + len(pool)
        struct.pack_into("<I", records, field.pointer_offset, pointer)
        pool.extend(encoded)
        pool.append(0)

    while (len(records) + len(pool)) % 4:
        pool.append(0)
    return bytes(records + pool)


def _validate_pool(data: bytes, pool_offset: int, strings: list[StringField]) -> None:
    expected = pool_offset
    for field in strings:
        pointer = struct.unpack_from("<I", data, field.pointer_offset)[0]
        if pointer != expected:
            raise BinTableError(
                f"Non-contiguous string pool at row {field.row}, column {field.column}: "
                f"0x{pointer:X} != 0x{expected:X}"
            )
        expected = data.index(0, pointer) + 1
    padding = data[expected:]
    if len(padding) > 3 or any(padding) or len(data) % 4:
        raise BinTableError("BIN table has unexpected data after its string pool")
