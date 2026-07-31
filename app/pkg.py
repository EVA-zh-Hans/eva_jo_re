from __future__ import annotations

import mmap
import os
import shutil
import struct
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping


SECTOR_SIZE = 0x800
BPK_HEADER = struct.Struct("<4sIIII")
RAW_DIRECTORY = struct.Struct("<IHHIII")
RAW_ENTRY = struct.Struct("<IIII")
BDL_HEADER = struct.Struct("<4sIIII12s")


class PkgError(Exception):
    pass


def align_up(value: int, alignment: int) -> int:
    return (value + alignment - 1) & ~(alignment - 1)


@dataclass(frozen=True)
class BpkHeader:
    magic: bytes
    unknown: int
    directory_offset: int
    directory_entry_diff: int
    entry_offset: int


@dataclass(frozen=True)
class BdlHeader:
    magic: bytes
    file_size: int
    compressed_size: int
    unknown1: int
    unknown2: int
    padding: bytes

    @property
    def stored_size(self) -> int:
        return self.compressed_size or self.file_size

    def pack(self) -> bytes:
        return BDL_HEADER.pack(
            self.magic,
            self.file_size,
            self.compressed_size,
            self.unknown1,
            self.unknown2,
            self.padding,
        )


@dataclass(frozen=True)
class Entry:
    path: PurePosixPath
    file_name_raw: bytes
    raw_record_offset: int
    unknown0: int
    allocated_size: int
    file_size: int
    data_offset: int
    bdl: BdlHeader

    @property
    def is_text(self) -> bool:
        return self.path.suffix.upper() in {".NUT", ".XML"}


@dataclass(frozen=True)
class Directory:
    name: str
    name_raw: bytes
    unknown0: int
    unknown1: int
    original_entry_offset: int
    original_size: int
    zero: int
    entries: tuple[Entry, ...]


class Archive:
    """Read-only, mmap-backed NEVA.PKG index."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._stream = None
        self._map = None
        self.header: BpkHeader
        self.directories: tuple[Directory, ...]
        self.entries: tuple[Entry, ...]
        self._entries_by_path: dict[PurePosixPath, tuple[Entry, ...]]

    def __enter__(self) -> "Archive":
        self._stream = self.path.open("rb")
        self._map = mmap.mmap(self._stream.fileno(), 0, access=mmap.ACCESS_READ)
        self._parse()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._map is not None:
            self._map.close()
        if self._stream is not None:
            self._stream.close()
        self._map = None
        self._stream = None

    @property
    def data(self) -> mmap.mmap:
        if self._map is None:
            raise RuntimeError("Archive must be opened with a context manager")
        return self._map

    def get(self, path: str | PurePosixPath) -> Entry:
        key = PurePosixPath(path)
        try:
            matches = self._entries_by_path[key]
        except KeyError as exc:
            raise PkgError(f"PKG entry does not exist: {key}") from exc
        if len(matches) != 1:
            raise PkgError(f"PKG path is ambiguous ({len(matches)} entries): {key}")
        return matches[0]

    def text_entries(self) -> Iterable[Entry]:
        return (entry for entry in self.entries if entry.is_text)

    def stored_payload(self, entry: Entry) -> bytes:
        start = entry.data_offset + BDL_HEADER.size
        self._check_range(start, entry.bdl.stored_size, str(entry.path))
        return bytes(self.data[start : start + entry.bdl.stored_size])

    def read(self, entry: Entry | str | PurePosixPath) -> bytes:
        if not isinstance(entry, Entry):
            entry = self.get(entry)
        payload = self.stored_payload(entry)
        try:
            result = zlib.decompress(payload) if entry.bdl.compressed_size else payload
        except zlib.error as exc:
            raise PkgError(f"Invalid zlib stream in {entry.path}: {exc}") from exc
        if len(result) != entry.bdl.file_size:
            raise PkgError(
                f"Unexpected size for {entry.path}: {len(result)} != {entry.bdl.file_size}"
            )
        return result

    def _parse(self) -> None:
        if len(self.data) < BPK_HEADER.size:
            raise PkgError("PKG is smaller than its BPK0 header")
        self.header = BpkHeader(*BPK_HEADER.unpack_from(self.data, 0))
        if self.header.magic != b"BPK0":
            raise PkgError(f"Expected BPK0 header, got {self.header.magic!r}")
        if not (
            BPK_HEADER.size
            <= self.header.entry_offset
            <= self.header.directory_offset
            < len(self.data)
        ):
            raise PkgError("BPK0 index offsets are out of range")

        position = self.header.directory_offset
        directories: list[Directory] = []
        all_entries: list[Entry] = []
        while position < len(self.data):
            self._check_range(position, RAW_DIRECTORY.size, "directory record")
            unknown0, unknown1, count, entry_offset, size, zero = RAW_DIRECTORY.unpack_from(
                self.data, position
            )
            name_raw, position = self._c_string(position + RAW_DIRECTORY.size)
            position = align_up(position, 4)
            try:
                name = name_raw.decode("cp932", errors="strict")
            except UnicodeDecodeError as exc:
                raise PkgError("Invalid CP932 directory name") from exc

            entries: list[Entry] = []
            if count:
                self._check_range(entry_offset, count * RAW_ENTRY.size, f"entry table {name}")
                file_name_position = entry_offset + count * RAW_ENTRY.size
                for index in range(count):
                    record_offset = entry_offset + index * RAW_ENTRY.size
                    unknown, allocated, file_size, data_offset = RAW_ENTRY.unpack_from(
                        self.data, record_offset
                    )
                    file_name_raw, file_name_position = self._c_string(file_name_position)
                    try:
                        file_name = file_name_raw.decode("cp932", errors="strict")
                    except UnicodeDecodeError as exc:
                        raise PkgError(f"Invalid CP932 file name in {name}") from exc
                    self._check_range(data_offset, BDL_HEADER.size, f"BDL0 {name}/{file_name}")
                    bdl = BdlHeader(*BDL_HEADER.unpack_from(self.data, data_offset))
                    if bdl.magic != b"BDL0":
                        raise PkgError(f"Expected BDL0 at 0x{data_offset:X} for {name}/{file_name}")
                    path = PurePosixPath(file_name) if name == "." else PurePosixPath(name) / file_name
                    entry = Entry(
                        path=path,
                        file_name_raw=file_name_raw,
                        raw_record_offset=record_offset,
                        unknown0=unknown,
                        allocated_size=allocated,
                        file_size=file_size,
                        data_offset=data_offset,
                        bdl=bdl,
                    )
                    entries.append(entry)
                    all_entries.append(entry)
            directories.append(
                Directory(
                    name=name,
                    name_raw=name_raw,
                    unknown0=unknown0,
                    unknown1=unknown1,
                    original_entry_offset=entry_offset,
                    original_size=size,
                    zero=zero,
                    entries=tuple(entries),
                )
            )

        self.directories = tuple(directories)
        self.entries = tuple(all_entries)
        grouped: dict[PurePosixPath, list[Entry]] = {}
        for entry in all_entries:
            grouped.setdefault(entry.path, []).append(entry)
        self._entries_by_path = {path: tuple(matches) for path, matches in grouped.items()}

    def _c_string(self, position: int) -> tuple[bytes, int]:
        end = self.data.find(b"\0", position)
        if end < 0:
            raise PkgError(f"Unterminated string at 0x{position:X}")
        return bytes(self.data[position:end]), end + 1

    def _check_range(self, offset: int, length: int, label: str) -> None:
        if offset < 0 or length < 0 or offset + length > len(self.data):
            raise PkgError(f"Out-of-range {label}: 0x{offset:X}+0x{length:X}")


@dataclass(frozen=True)
class _Replacement:
    entry: Entry
    data: bytes
    header: BdlHeader
    payload: bytes

    @property
    def block_size(self) -> int:
        return BDL_HEADER.size + len(self.payload)


def _prepare(entry: Entry, data: bytes) -> _Replacement:
    payload = zlib.compress(data) if entry.bdl.compressed_size else data
    header = BdlHeader(
        magic=b"BDL0",
        file_size=len(data),
        compressed_size=len(payload) if entry.bdl.compressed_size else 0,
        unknown1=entry.bdl.unknown1,
        unknown2=entry.bdl.unknown2,
        padding=entry.bdl.padding,
    )
    return _Replacement(entry, data, header, payload)


def replace_entries(
    source: str | Path,
    output: str | Path,
    replacements: Mapping[str | PurePosixPath, bytes],
) -> str:
    """Create a patched PKG and return copy, fixed-layout, or rebuilt."""

    source_path = Path(source).resolve()
    output_path = Path(output).resolve()
    if source_path == output_path:
        raise PkgError("Source and output PKG paths must differ")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Archive(source_path) as archive:
        prepared = {
            PurePosixPath(path): _prepare(archive.get(path), data)
            for path, data in replacements.items()
        }
        if not prepared:
            _atomic_copy(source_path, output_path)
            return "copy"
        if all(item.block_size <= item.entry.allocated_size for item in prepared.values()):
            _replace_fixed(source_path, output_path, prepared.values())
            return "fixed-layout"
        _rebuild(archive, output_path, prepared)
        return "rebuilt"


def _atomic_copy(source: Path, output: Path) -> None:
    with tempfile.NamedTemporaryFile(dir=output.parent, prefix=f".{output.name}.", delete=False) as tmp:
        temporary = Path(tmp.name)
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def _replace_fixed(source: Path, output: Path, replacements: Iterable[_Replacement]) -> None:
    _atomic_copy(source, output)
    with output.open("r+b") as stream:
        for replacement in replacements:
            entry = replacement.entry
            stream.seek(entry.data_offset)
            stream.write(replacement.header.pack())
            stream.write(replacement.payload)
            stream.write(b"\0" * (entry.allocated_size - replacement.block_size))
            stream.seek(entry.raw_record_offset + 8)
            stream.write(struct.pack("<I", len(replacement.data)))


def _rebuild(
    archive: Archive,
    output: Path,
    replacements: Mapping[PurePosixPath, _Replacement],
) -> None:
    buffer = bytearray(SECTOR_SIZE)
    rebuilt_directories: list[tuple[Directory, list[tuple[Entry, int, int, int]]]] = []

    for directory in archive.directories:
        rebuilt_entries: list[tuple[Entry, int, int, int]] = []
        for entry in directory.entries:
            if len(buffer) % SECTOR_SIZE:
                buffer.extend(b"\0" * (align_up(len(buffer), SECTOR_SIZE) - len(buffer)))
            data_offset = len(buffer)
            replacement = replacements.get(entry.path)
            if replacement:
                header, payload, file_size = (
                    replacement.header,
                    replacement.payload,
                    len(replacement.data),
                )
            else:
                header, payload, file_size = entry.bdl, archive.stored_payload(entry), entry.bdl.file_size
            buffer.extend(header.pack())
            buffer.extend(payload)
            allocated = align_up(BDL_HEADER.size + len(payload), SECTOR_SIZE)
            rebuilt_entries.append((entry, data_offset, file_size, allocated))
        rebuilt_directories.append((directory, rebuilt_entries))

    if len(buffer) % 16:
        buffer.extend(b"\0" * (align_up(len(buffer), 16) - len(buffer)))
    entry_base = len(buffer)
    entry_locations: list[tuple[int, int]] = []
    for directory, rebuilt_entries in rebuilt_directories:
        block_start = len(buffer)
        for entry, data_offset, file_size, allocated in rebuilt_entries:
            buffer.extend(RAW_ENTRY.pack(entry.unknown0, allocated, file_size, data_offset))
        for entry, *_ in rebuilt_entries:
            buffer.extend(entry.file_name_raw + b"\0")
        if len(buffer) % 16:
            buffer.extend(b"\0" * (align_up(len(buffer), 16) - len(buffer)))
        entry_locations.append((block_start, len(buffer) - block_start))

    directory_offset = len(buffer)
    for (directory, rebuilt_entries), (entry_location, entry_size) in zip(
        rebuilt_directories, entry_locations, strict=True
    ):
        if not rebuilt_entries and directory.original_entry_offset == 0:
            entry_location = 0
            entry_size = 0
        buffer.extend(
            RAW_DIRECTORY.pack(
                directory.unknown0,
                directory.unknown1,
                len(rebuilt_entries),
                entry_location,
                entry_size,
                directory.zero,
            )
        )
        buffer.extend(directory.name_raw + b"\0")
        if len(buffer) % 4:
            buffer.extend(b"\0" * (align_up(len(buffer), 4) - len(buffer)))

    buffer[: BPK_HEADER.size] = BPK_HEADER.pack(
        b"BPK0",
        archive.header.unknown,
        directory_offset,
        directory_offset - entry_base,
        entry_base,
    )
    with tempfile.NamedTemporaryFile(dir=output.parent, prefix=f".{output.name}.", delete=False) as tmp:
        temporary = Path(tmp.name)
        tmp.write(buffer)
    try:
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
