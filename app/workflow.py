from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from . import font, iso, nut, paratranz, xml
from .encoding import DecodedText, decode
from .pkg import Archive, Entry, replace_entries


class WorkflowError(RuntimeError):
    pass


@dataclass
class _TextFile:
    entry: Entry
    decoded: DecodedText
    spans: list
    items: list[paratranz.SourceItem]
    rendered: str
    translations: dict[int, str]

    @property
    def changed(self) -> bool:
        return self.rendered != self.decoded.text


def export_translations(
    source_iso: Path,
    translations_dir: Path,
    work_dir: Path,
    report_path: Path,
) -> dict:
    pkg_path = _ensure_neva(source_iso, work_dir)
    counts = Counter()
    obsolete: list[dict] = []
    invalid_xml: list[dict] = []
    with Archive(pkg_path) as archive:
        for entry in archive.text_entries():
            decoded = decode(archive.read(entry))
            spans = _scan(entry.path, decoded.text)
            counts[f"{entry.path.suffix.upper()} files"] += 1
            counts[f"{decoded.encoding} files"] += 1
            if entry.path.suffix.upper() == ".XML":
                problem = xml.validation_error(decoded.text)
                if problem:
                    invalid_xml.append({"path": entry.path.as_posix(), "problem": problem})
            if not spans:
                continue
            items = _source_items(spans)
            result = paratranz.merge_file(translations_dir, entry.path, items)
            counts["translation files"] += 1
            counts["translation entries"] += result.total
            counts["preserved entries"] += result.preserved
            counts["new entries"] += result.added
            obsolete.extend(
                {"path": entry.path.as_posix(), **item} for item in result.obsolete
            )
    report = {
        "source_iso": str(source_iso),
        "source_iso_sha256": _sha256(source_iso),
        "pkg_sha256": _sha256(pkg_path),
        "counts": dict(sorted(counts.items())),
        "obsolete": obsolete,
        "nonstandard_xml": invalid_xml,
    }
    _write_json(report_path, report)
    return report


def check_translations(
    source_iso: Path,
    translations_dir: Path,
    work_dir: Path,
    report_path: Path,
) -> dict:
    pkg_path = _ensure_neva(source_iso, work_dir)
    files, errors = _load_text_files(pkg_path, translations_dir)
    expected = {paratranz.json_path(translations_dir, item.entry.path) for item in files if item.spans}
    actual = set(translations_dir.rglob("*.json")) if translations_dir.exists() else set()
    for unexpected in sorted(actual - expected):
        errors.append(f"Unexpected translation file: {unexpected}")
    translated = sum(len(item.translations) for item in files)
    report = {
        "ok": not errors,
        "files": len([item for item in files if item.spans]),
        "entries": sum(len(item.spans) for item in files),
        "translated_entries": translated,
        "errors": errors,
    }
    _write_json(report_path, report)
    if errors:
        raise WorkflowError(f"Translation validation failed with {len(errors)} error(s)")
    return report


def build_image(
    source_iso: Path,
    translations_dir: Path,
    overrides_dir: Path,
    build_dir: Path,
    output_iso: Path,
) -> dict:
    work_dir = source_iso.parent / "cache" / source_iso.stem
    pkg_path = _ensure_neva(source_iso, work_dir)
    files, errors = _load_text_files(pkg_path, translations_dir)
    if errors:
        report = {"ok": False, "errors": errors}
        _write_json(build_dir / "reports" / "build.json", report)
        raise WorkflowError(f"Translation validation failed with {len(errors)} error(s)")

    generated = build_dir / "generated"
    reports = build_dir / "reports"
    generated.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)

    # Preserve every original glyph and every glyph used directly by the final
    # text. A CP932 character in rendered translations must keep its original
    # JIS2UCS entry instead of being reused as a substitution slot.
    reserved = set().union(
        *(set(item.decoded.text) | set(item.rendered) for item in files)
    )
    cp932_outputs = [item.rendered for item in files if item.changed and item.decoded.encoding == "cp932"]
    required = font.required_substitutions(cp932_outputs)
    with Archive(pkg_path) as archive:
        original_table = archive.read("FONT/JIS2UCS.BIN")
    mapping_path = generated / "charset-map.json"
    plan = font.build_plan(original_table, required, reserved, mapping_path)
    _write_json(mapping_path, plan.mapping_json())
    _write_json(reports / "charset.json", plan.report_json())
    (generated / "JIS2UCS.BIN").write_bytes(plan.table)

    replacements: dict[PurePosixPath, bytes] = {}
    changed_paths: list[str] = []
    for item in files:
        if not item.changed:
            continue
        substitutions = plan.substitutions if item.decoded.encoding == "cp932" else None
        replacements[item.entry.path] = item.decoded.with_text(item.rendered).encode(substitutions)
        changed_paths.append(item.entry.path.as_posix())
    if plan.mappings:
        replacements[PurePosixPath("FONT/JIS2UCS.BIN")] = plan.table

    output_pkg = generated / "NEVA.PKG"
    strategy = replace_entries(pkg_path, output_pkg, replacements)
    overlay = build_dir / "overlay"
    if overlay.exists():
        shutil.rmtree(overlay)
    overlay.mkdir(parents=True)
    if overrides_dir.exists():
        shutil.copytree(overrides_dir, overlay, dirs_exist_ok=True)
    pkg_overlay = overlay / "PSP_GAME" / "USRDIR" / "NEVA.PKG"
    pkg_overlay.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(output_pkg, pkg_overlay)

    static_overrides = [path for path in overlay.rglob("*") if path.is_file() and path != pkg_overlay]
    output_iso.parent.mkdir(parents=True, exist_ok=True)
    if not replacements and not static_overrides:
        shutil.copyfile(source_iso, output_iso)
        image_strategy = "copy"
    else:
        iso.repack_overlay(source_iso, output_iso, overlay)
        image_strategy = "sparse-overlay"

    report = {
        "ok": True,
        "source_iso_sha256": _sha256(source_iso),
        "output_iso_sha256": _sha256(output_iso),
        "source_pkg_sha256": _sha256(pkg_path),
        "output_pkg_sha256": _sha256(output_pkg),
        "pkg_strategy": strategy,
        "image_strategy": image_strategy,
        "changed_text_files": changed_paths,
        "changed_text_count": len(changed_paths),
        "font_mapping_count": len(plan.mappings),
    }
    _write_json(reports / "build.json", report)
    return report


def verify_image(
    source_iso: Path,
    patched_iso: Path,
    translations_dir: Path,
    report_path: Path,
) -> dict:
    errors: list[str] = []
    changed: list[str] = []
    allowed = _translated_source_paths(translations_dir)
    allowed.add(PurePosixPath("FONT/JIS2UCS.BIN"))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=report_path.parent) as directory:
        temporary = Path(directory)
        source_pkg = temporary / "source.pkg"
        patched_pkg = temporary / "patched.pkg"
        iso.extract_neva(source_iso, source_pkg)
        iso.extract_neva(patched_iso, patched_pkg)
        with Archive(source_pkg) as source, Archive(patched_pkg) as patched:
            if len(source.directories) != len(patched.directories):
                errors.append("Directory count changed")
            if len(source.entries) != len(patched.entries):
                errors.append("Entry count changed")
            for index, (old, new) in enumerate(zip(source.entries, patched.entries)):
                if old.path != new.path:
                    errors.append(f"Entry order changed at {index}: {old.path} != {new.path}")
                    continue
                try:
                    patched.read(new)
                except Exception as exc:
                    errors.append(f"Cannot read {new.path}: {exc}")
                    continue
                old_block = old.bdl.pack() + source.stored_payload(old)
                new_block = new.bdl.pack() + patched.stored_payload(new)
                if old_block != new_block:
                    changed.append(new.path.as_posix())
                    if new.path not in allowed:
                        errors.append(f"Unexpected modified PKG entry: {new.path}")
    report = {
        "ok": not errors,
        "source_iso_sha256": _sha256(source_iso),
        "patched_iso_sha256": _sha256(patched_iso),
        "changed_pkg_entries": changed,
        "errors": errors,
    }
    _write_json(report_path, report)
    if errors:
        raise WorkflowError(f"Image verification failed with {len(errors)} error(s)")
    return report


def _load_text_files(pkg_path: Path, translations_dir: Path) -> tuple[list[_TextFile], list[str]]:
    files: list[_TextFile] = []
    errors: list[str] = []
    with Archive(pkg_path) as archive:
        for entry in archive.text_entries():
            decoded = decode(archive.read(entry))
            spans = _scan(entry.path, decoded.text)
            items = _source_items(spans)
            translations: dict[int, str] = {}
            if spans:
                json_file = paratranz.json_path(translations_dir, entry.path)
                if not json_file.exists():
                    errors.append(f"Missing translation file: {json_file}")
                else:
                    translations, item_errors = paratranz.translations_for(
                        translations_dir, entry.path, items
                    )
                    errors.extend(item_errors)
            rendered = _replace(entry.path, decoded.text, spans, translations)
            files.append(_TextFile(entry, decoded, spans, items, rendered, translations))
    return files, errors


def _scan(path: PurePosixPath, text: str) -> list:
    return nut.scan(text) if path.suffix.upper() == ".NUT" else xml.scan(text)


def _replace(path: PurePosixPath, text: str, spans: list, translations: dict[int, str]) -> str:
    return nut.replace(text, spans, translations) if path.suffix.upper() == ".NUT" else xml.replace(text, spans, translations)


def _source_items(spans: list) -> list[paratranz.SourceItem]:
    return [paratranz.SourceItem(span.ordinal, span.original, span.context) for span in spans]


def _ensure_neva(source_iso: Path, work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    pkg_path = work_dir / "NEVA.PKG"
    marker = work_dir / "source.json"
    source_hash = _sha256(source_iso)
    if pkg_path.exists() and marker.exists():
        try:
            state = json.loads(marker.read_text(encoding="utf-8"))
            if state.get("source_iso_sha256") == source_hash:
                return pkg_path
        except (OSError, json.JSONDecodeError):
            pass
    iso.extract_neva(source_iso, pkg_path)
    _write_json(marker, {"source_iso_sha256": source_hash, "pkg_sha256": _sha256(pkg_path)})
    return pkg_path


def _translated_source_paths(root: Path) -> set[PurePosixPath]:
    paths: set[PurePosixPath] = set()
    if not root.exists():
        return paths
    for path in root.rglob("*.json"):
        try:
            if not any(entry.get("translation") for entry in paratranz.load(path)):
                continue
        except paratranz.ParaTranzError:
            continue
        relative = path.relative_to(root).as_posix()
        paths.add(PurePosixPath(relative[:-5]))
    return paths


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
