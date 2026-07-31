from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path


class FontError(ValueError):
    pass


@dataclass(frozen=True)
class Mapping:
    target: str
    slot: str
    index: int
    cp932: str


@dataclass(frozen=True)
class Plan:
    substitutions: dict[str, str]
    table: bytes
    mappings: tuple[Mapping, ...]
    required: tuple[str, ...]
    available_slots: int
    reused_slots: int

    def mapping_json(self) -> dict:
        return {
            "schema": 1,
            "mapping": [mapping.__dict__ for mapping in self.mappings],
        }

    def report_json(self) -> dict:
        return {
            "required_characters": len(self.required),
            "available_slots": self.available_slots,
            "assigned_slots": len(self.mappings),
            "reused_slots": self.reused_slots,
            "remaining_slots": self.available_slots - len(self.mappings),
            "characters": list(self.required),
        }


def required_substitutions(texts: list[str]) -> set[str]:
    required: set[str] = set()
    for text in texts:
        for char in text:
            try:
                char.encode("cp932", errors="strict")
            except UnicodeEncodeError:
                required.add(char)
    return required


def build_plan(
    original_table: bytes,
    required: set[str],
    reserved: set[str],
    previous_mapping: Path | None = None,
) -> Plan:
    if len(original_table) % 2:
        raise FontError("JIS2UCS.BIN length must be divisible by two")
    codepoints = list(struct.unpack(f"<{len(original_table) // 2}H", original_table))
    slots: list[tuple[str, int, str]] = []
    seen: set[str] = set()
    for index, codepoint in enumerate(codepoints):
        char = chr(codepoint)
        if char in seen or char in reserved:
            continue
        try:
            encoded = char.encode("cp932", errors="strict")
        except UnicodeEncodeError:
            continue
        if len(encoded) != 2 or not (0x88 <= encoded[0] <= 0x9F or 0xE0 <= encoded[0] <= 0xEA):
            continue
        seen.add(char)
        slots.append((char, index, encoded.hex()))

    ordered_required = tuple(sorted(required, key=ord))
    if any(ord(char) > 0xFFFF for char in ordered_required):
        unsupported = [char for char in ordered_required if ord(char) > 0xFFFF]
        raise FontError(f"JIS2UCS.BIN cannot store supplementary characters: {unsupported!r}")
    if len(ordered_required) > len(slots):
        missing = len(ordered_required) - len(slots)
        raise FontError(
            f"Font table capacity exceeded: need {len(ordered_required)}, "
            f"have {len(slots)}, missing {missing}"
        )

    slots_by_char = {slot: (slot, index, encoded) for slot, index, encoded in slots}
    assignments: dict[str, tuple[str, int, str]] = {}
    used_slots: set[str] = set()
    reused = 0
    if previous_mapping and previous_mapping.exists():
        try:
            previous = json.loads(previous_mapping.read_text(encoding="utf-8"))
            for item in previous.get("mapping", []):
                target = item.get("target")
                slot = item.get("slot")
                if target in required and slot in slots_by_char and slot not in used_slots:
                    assignments[target] = slots_by_char[slot]
                    used_slots.add(slot)
                    reused += 1
        except (OSError, json.JSONDecodeError, TypeError):
            assignments.clear()
            used_slots.clear()
            reused = 0

    free_slots = (slot for slot in slots if slot[0] not in used_slots)
    for target in ordered_required:
        if target not in assignments:
            assignments[target] = next(free_slots)

    mappings: list[Mapping] = []
    for target in ordered_required:
        slot, index, encoded = assignments[target]
        codepoints[index] = ord(target)
        mappings.append(Mapping(target, slot, index, encoded))
    table = struct.pack(f"<{len(codepoints)}H", *codepoints)
    substitutions = {mapping.target: mapping.slot for mapping in mappings}
    return Plan(
        substitutions=substitutions,
        table=table,
        mappings=tuple(mappings),
        required=ordered_required,
        available_slots=len(slots),
        reused_slots=reused,
    )
