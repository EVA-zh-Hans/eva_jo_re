from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from . import paratranz
from .encoding import EncodingError, encode_game_text


class EbootPatchError(ValueError):
    pass


@dataclass(frozen=True)
class Entry:
    key: str
    offset: int
    original: str
    translation: str
    context: str


UTF8_REPLACEMENTS = (
    (0x0027A16C, "「使徒、襲来」", "「使徒、来袭」"),
    (0x0027A184, "「見知らぬ、天井」", "「陌生的天花板」"),
    (0x0027A1A0, "「鳴らない、電話」", "「不响的电话」"),
    (0x0027A1BC, "「レイ、心のむこうに」", "「丽、心的彼端」"),
    (0x0027A1E0, "「人の造りしもの」", "「人造之物」"),
    (0x0027A1FC, "「アスカ、来日」", "「明日香、来日」"),
    (0x0027A218, "「瞬間、心、重ねて」", "「瞬间、心灵、重叠」"),
    (0x0027A238, "「マグマダイバー」", "「岩浆潜行者」"),
    (0x0027A254, "「静止した闇の中で」", "「在静止的黑暗中」"),
    (0x0027A274, "「奇跡の価値は」", "「奇迹的价值」"),
    (0x0027A290, "「使徒、侵入」", "「使徒、入侵」"),
    (0x0027A2A8, "「死に至る病、そして」", "「致死的疾病、而后」"),
    (0x0027A2CC, "「四人目の適格者」", "「第四适格者」"),
    (0x0027A2E8, "「男の戦い」", "男人的战斗"),
    (0x0027A2FC, "「嘘と沈黙」", "谎言与沉默"),
    (0x0027A310, "「せめて、人間らしく」", "「至少像个人类」"),
    (0x0027A334, "「涙」", "「泪」"),
    (0x0027A340, "「最後のシ者」", "「最后的使者」"),
    (0x0027A358, "「まごころを、君に」", "「真心为你」"),
    (0x0027A380, "　戦闘前日常", "　战斗前日常"),
    (0x0027A394, "　戦闘直前", "　战斗前夕"),
    (0x0027A3A4, "　戦闘後", "　战斗后"),
    (0x0027A3B4, "　戦闘後日常", "　战斗后日常"),
    (0x0027A3C8, "　終了", "　结束"),
    (0x0027A3D4, "　ゲームクリア", "　游戏通关"),
    (0x00282C70, "EVANGELION　ヱヴァンゲリヲン：序", "EVANGELION　新世纪福音战士：序"),
    (0x00282C9C, "セーブデータ", "保存数据"),
)


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
        try:
            encoded = encode_game_text(entry.translation, substitutions)
        except EncodingError as exc:
            raise EbootPatchError(f"Cannot encode translation for {entry.key}: {exc}") from exc
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


def replace_utf8(data: bytes) -> bytes:
    output = bytearray(data)
    for offset, original, translation in UTF8_REPLACEMENTS:
        original_size = len(original.encode("utf-8"))
        encoded = translation.encode("utf-8")
        output[offset : offset + original_size] = encoded.ljust(original_size, b"\0")
    return bytes(output)


def verify_utf8(data: bytes) -> list[str]:
    errors: list[str] = []
    for offset, original, translation in UTF8_REPLACEMENTS:
        original_size = len(original.encode("utf-8"))
        expected = translation.encode("utf-8").ljust(original_size, b"\0")
        if data[offset : offset + original_size] != expected:
            errors.append(f"UTF-8 EBOOT entry was not translated at 0x{offset:08X}")
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
