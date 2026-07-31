from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable


CONTROL = re.compile(r"\\[nrt]|\$[A-Za-z][A-Za-z0-9_]*|<[^>]+>|[▽△]")
LAYOUT_CONTROLS = {r"\n", r"\r", r"\t"}


class ParaTranzError(ValueError):
    pass


@dataclass(frozen=True)
class SourceItem:
    ordinal: int
    original: str
    context: str


@dataclass(frozen=True)
class MergeResult:
    total: int
    preserved: int
    added: int
    obsolete: tuple[dict, ...]


def key_for(path: PurePosixPath, item: SourceItem) -> str:
    path_hash = hashlib.sha256(path.as_posix().encode("utf-8")).hexdigest()[:10]
    source_hash = hashlib.sha256(item.original.encode("utf-8")).hexdigest()[:10]
    return f"e_{path_hash}_{item.ordinal:04d}_{source_hash}"


def json_path(root: Path, source_path: PurePosixPath) -> Path:
    return root.joinpath(*source_path.parts[:-1], source_path.name + ".json")


def merge_file(
    root: Path,
    source_path: PurePosixPath,
    items: Iterable[SourceItem],
) -> MergeResult:
    output = json_path(root, source_path)
    previous = load(output) if output.exists() else []
    previous_by_key = {entry["key"]: entry for entry in previous}
    generated: list[dict] = []
    preserved = 0
    added = 0
    current_keys: set[str] = set()

    for item in items:
        key = key_for(source_path, item)
        current_keys.add(key)
        old = previous_by_key.get(key)
        entry = {
            "key": key,
            "original": item.original,
            "translation": "",
            "context": f"File: {source_path.as_posix()}\n{item.context}",
        }
        if old and old.get("original") == item.original:
            entry["translation"] = old.get("translation", "")
            if "stage" in old:
                entry["stage"] = old["stage"]
            preserved += 1
        else:
            added += 1
        generated.append(entry)

    obsolete = tuple(entry for entry in previous if entry["key"] not in current_keys)
    _write_json(output, generated)
    return MergeResult(len(generated), preserved, added, obsolete)


def load(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ParaTranzError(f"Cannot read ParaTranz JSON {path}: {exc}") from exc
    if not isinstance(data, list):
        raise ParaTranzError(f"ParaTranz file must contain a JSON array: {path}")
    seen: set[str] = set()
    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ParaTranzError(f"Entry {index} is not an object: {path}")
        for field in ("key", "original", "translation"):
            if not isinstance(entry.get(field), str):
                raise ParaTranzError(f"Entry {index} has invalid {field}: {path}")
        if entry["key"] in seen:
            raise ParaTranzError(f"Duplicate key {entry['key']} in {path}")
        seen.add(entry["key"])
    return data


def translations_for(
    root: Path,
    source_path: PurePosixPath,
    items: Iterable[SourceItem],
) -> tuple[dict[int, str], list[str]]:
    path = json_path(root, source_path)
    if not path.exists():
        return {}, []
    entries = load(path)
    by_key = {entry["key"]: entry for entry in entries}
    expected: set[str] = set()
    translations: dict[int, str] = {}
    errors: list[str] = []
    for item in items:
        key = key_for(source_path, item)
        expected.add(key)
        entry = by_key.get(key)
        if entry is None:
            errors.append(f"{source_path}: missing key {key}")
            continue
        if entry["original"] != item.original:
            errors.append(f"{source_path}: original mismatch for {key}")
            continue
        translation = entry.get("translation", "")
        if translation:
            source_controls = [
                value for value in CONTROL.findall(item.original) if value not in LAYOUT_CONTROLS
            ]
            translated_controls = [
                value for value in CONTROL.findall(translation) if value not in LAYOUT_CONTROLS
            ]
            if Counter(source_controls) != Counter(translated_controls):
                errors.append(
                    f"{source_path}: control sequence mismatch for {key}: "
                    f"{source_controls!r} != {translated_controls!r}"
                )
                continue
            translations[item.ordinal] = translation
    for key in by_key.keys() - expected:
        errors.append(f"{source_path}: obsolete key {key}")
    return translations, errors


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as temporary:
        temporary.write(serialized)
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
