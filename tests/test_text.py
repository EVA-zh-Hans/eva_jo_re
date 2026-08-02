import json
import struct
import tempfile
import unittest
from pathlib import Path, PurePosixPath

from app import aitalklist, bintable, eboot_patch, font, nut, paratranz, xml
from app.encoding import EncodingError, decode, encode_game_text, is_game_safe_cp932


def _make_bin_table(rows: list[tuple[str, int, str]]) -> bytes:
    field_types = (4, 0, 4)
    record_offset = bintable.HEADER.size + len(field_types) * 4
    record_size = sum(bintable.TYPE_WIDTHS[field_type] for field_type in field_types)
    pool_offset = record_offset + len(rows) * record_size
    output = bytearray(
        bintable.HEADER.pack(1, record_offset, len(rows), len(field_types), bintable.HEADER.size)
    )
    output.extend(struct.pack("<3I", *field_types))
    pool = bytearray()
    for name, value, description in rows:
        name_pointer = pool_offset + len(pool)
        pool.extend(name.encode("cp932") + b"\0")
        description_pointer = pool_offset + len(pool)
        pool.extend(description.encode("cp932") + b"\0")
        output.extend(struct.pack("<III", name_pointer, value, description_pointer))
    output.extend(pool)
    while len(output) % 4:
        output.append(0)
    return bytes(output)


class NutTests(unittest.TestCase):
    def test_scans_raw_japanese_outside_comments(self):
        source = (
            '// im.event(IMC_REI, @"コメント");\n'
            'local broken = ";\n'
            'im.event(IMC_REI, @"本物\\nです", "voice_01");\n'
        )
        spans = nut.scan(source)
        self.assertEqual([span.original for span in spans], [r"本物\nです"])
        self.assertIn("Call: im.event", spans[0].context)
        self.assertIn("Speaker: IMC_REI", spans[0].context)
        self.assertIn("Voice: voice_01", spans[0].context)

    def test_replaces_exact_span_and_renders_newline_escape(self):
        source = 'im.play(IMC_NONE, @"原文");\n'
        rendered = nut.replace(source, nut.scan(source), {1: "第一行\n第二行"})
        self.assertEqual(rendered, 'im.play(IMC_NONE, @"第一行\\n第二行");\n')


class XmlTests(unittest.TestCase):
    def test_tolerates_game_comments_and_preserves_them(self):
        source = '<?xml version="1.0"?>\n<!--壊れたコメント->\n<R text="日本語">本文</R>'
        spans = xml.scan(source)
        self.assertEqual([span.original for span in spans], ["日本語", "本文"])
        rendered = xml.replace(
            source,
            spans,
            {spans[0].ordinal: "中文&值", spans[1].ordinal: "正文"},
        )
        self.assertIn('text="中文&值"', rendered)
        self.assertIn(">正文</R>", rendered)
        self.assertIn("<!--壊れたコメント->", rendered)

    def test_reports_nonstandard_xml_without_blocking_scan(self):
        source = "<ROOT><!--bad-><VALUE>日本語</VALUE></ROOT>"
        self.assertIsNotNone(xml.validation_error(source))
        self.assertEqual(len(xml.scan(source)), 1)

    def test_preserves_game_attribute_values_verbatim(self):
        source = '<R text="日本語"/>'
        span = xml.scan(source)[0]
        rendered = xml.replace(source, [span], {span.ordinal: "A&B <test> 'ok'"})
        self.assertEqual(rendered, '<R text="A&B <test> \'ok\'"/>')

    def test_rejects_double_quote_in_game_attribute(self):
        source = '<R text="日本語"/>'
        span = xml.scan(source)[0]
        with self.assertRaisesRegex(xml.XmlError, "unsupported double quote"):
            xml.replace(source, [span], {span.ordinal: 'A"B'})

    def test_does_not_decode_entities_in_game_attributes(self):
        source = '<R text="日本語&amp;"/>'
        span = xml.scan(source)[0]
        self.assertEqual(span.original, "日本語&amp;")
        self.assertEqual(xml.replace(source, [span], {span.ordinal: span.original}), source)


class ParaTranzTests(unittest.TestCase):
    def test_incremental_merge_preserves_translation_and_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = PurePosixPath("BTL/TEST.NUT")
            items = [paratranz.SourceItem(1, "原文", "Line: 1")]
            paratranz.merge_file(root, path, items)
            output = paratranz.json_path(root, path)
            data = json.loads(output.read_text(encoding="utf-8"))
            data[0]["translation"] = "译文"
            data[0]["stage"] = 1
            output.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            result = paratranz.merge_file(root, path, items)
            merged = paratranz.load(output)
            self.assertEqual(result.preserved, 1)
            self.assertEqual(merged[0]["translation"], "译文")
            self.assertEqual(merged[0]["stage"], 1)

    def test_layout_newlines_may_change_but_semantic_markers_must_remain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = PurePosixPath("FREE/TEST.NUT")
            item = paratranz.SourceItem(1, r"原文\n继续▽", "Line: 1")
            paratranz.merge_file(root, path, [item])
            output = paratranz.json_path(root, path)
            data = paratranz.load(output)
            data[0]["translation"] = "译文继续▽"
            output.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            translations, errors = paratranz.translations_for(root, path, [item])
            self.assertFalse(errors)
            self.assertEqual(translations[1], "译文继续▽")
            data[0]["translation"] = "译文继续"
            output.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            _, errors = paratranz.translations_for(root, path, [item])
            self.assertEqual(len(errors), 1)

    def test_printf_placeholders_must_remain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = PurePosixPath("ADJUST/TEST.BIN")
            item = paratranz.SourceItem(1, "武器%s", "Row: 0")
            paratranz.merge_file(root, path, [item])
            output = paratranz.json_path(root, path)
            data = paratranz.load(output)
            data[0]["translation"] = "武器"
            output.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            _, errors = paratranz.translations_for(root, path, [item])
            self.assertEqual(len(errors), 1)


class BinTableTests(unittest.TestCase):
    def test_scans_rebuilds_and_updates_string_pointers(self):
        source = _make_bin_table([("武器", 7, "説明"), ("ASCII", 9, "")])
        table = bintable.parse(source)
        spans = bintable.scan(table, {0: "name", 2: "description"})
        self.assertEqual([span.original for span in spans], ["武器", "説明"])
        self.assertIn("Row: 0", spans[0].context)
        rendered = bintable.render(
            table,
            spans,
            {spans[0].ordinal: "测试", spans[1].ordinal: "新说明"},
        )
        rebuilt = bintable.replace(
            table,
            rendered,
            {"测": "亜", "试": "唖", "说": "娃", "明": "阿"},
        )
        parsed = bintable.parse(rebuilt)
        self.assertEqual(parsed.strings[0].original, "亜唖")
        self.assertEqual(parsed.strings[1].original, "新娃阿")
        self.assertNotEqual(rebuilt, source)

    def test_noop_is_byte_identical(self):
        source = _make_bin_table([("武器", 7, "説明")])
        table = bintable.parse(source)
        spans = bintable.scan(table, {0: "name", 2: "description"})
        self.assertEqual(bintable.replace(table, bintable.render(table, spans, {})), source)

    def test_preserves_real_and_escaped_newlines(self):
        source = _make_bin_table([("武器", 7, "説明")])
        table = bintable.parse(source)
        spans = bintable.scan(table, {0: "name", 2: "description"})
        rendered = bintable.render(
            table,
            spans,
            {spans[0].ordinal: "第一行\n第二行", spans[1].ordinal: r"第一行\n第二行"},
        )
        self.assertEqual(rendered[0], "第一行\n第二行")
        self.assertEqual(rendered[1], r"第一行\n第二行")

    def test_rejects_non_contiguous_string_pool(self):
        source = bytearray(_make_bin_table([("武器", 7, "説明")]))
        source.insert(-1, 0)
        with self.assertRaisesRegex(bintable.BinTableError, "unexpected data"):
            bintable.parse(bytes(source))


class AiTalkListTests(unittest.TestCase):
    def _source(self) -> bytes:
        records = []
        for text, character in [("挨拶する", ""), ("怪我について話す", "rei")]:
            record = bytearray(aitalklist.RECORD_SIZE)
            encoded = text.encode("cp932")
            record[: len(encoded)] = encoded
            encoded_character = character.encode("ascii")
            start = aitalklist.CHARACTER_OFFSET
            record[start : start + len(encoded_character)] = encoded_character
            records.append(bytes(record))
        return b"".join([*records, aitalklist.SENTINEL])

    def test_scans_and_replaces_fixed_record_text(self):
        source = self._source()
        table = aitalklist.parse(source)
        spans = aitalklist.scan(table)
        self.assertEqual(
            [span.original for span in spans], ["挨拶する", "怪我について話す"]
        )
        self.assertIn("Character ID: rei", spans[1].context)
        rendered = aitalklist.render(
            table,
            spans,
            {spans[0].ordinal: "打招呼", spans[1].ordinal: "谈谈受伤的事"},
        )
        patched = aitalklist.replace(
            table,
            rendered,
            {
                "打": "亜",
                "招": "唖",
                "呼": "娃",
                "谈": "阿",
                "伤": "哀",
                "事": "愛",
            },
        )
        self.assertEqual(len(patched), len(source))
        self.assertEqual(patched[-aitalklist.RECORD_SIZE :], aitalklist.SENTINEL)
        self.assertEqual(aitalklist.parse(patched).strings[0].original, "亜唖娃")

    def test_rejects_translation_that_exceeds_slot(self):
        table = aitalklist.parse(self._source())
        rendered = ("あ" * 16, table.strings[1].original)
        with self.assertRaisesRegex(aitalklist.AiTalkListError, "allows 31"):
            aitalklist.replace(table, rendered)

    def test_noop_is_byte_identical(self):
        source = self._source()
        table = aitalklist.parse(source)
        self.assertEqual(
            aitalklist.replace(
                table, aitalklist.render(table, aitalklist.scan(table), {})
            ),
            source,
        )


class EbootPatchTests(unittest.TestCase):
    def _write_entries(self, root: Path, entries: list[dict]) -> Path:
        path = root / "EBOOT.BIN.json"
        path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
        return path

    def test_validates_source_offset_and_replaces_in_place(self):
        source = b"HEAD" + "予算".encode("cp932") + b"\0TAIL"
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_entries(
                Path(directory),
                [
                    {
                        "key": "eboot_00000004",
                        "offset": 4,
                        "original": "予算",
                        "translation": "预算",
                        "context": "test",
                    }
                ],
            )
            patch_set = eboot_patch.load(source, path)
            patched = eboot_patch.replace(patch_set, {"预": "亜"})
            self.assertEqual(patched[4:8], "亜算".encode("cp932"))
            self.assertEqual(len(patched), len(source))

    def test_rejects_offset_that_does_not_match_source(self):
        source = b"HEAD" + "予算".encode("cp932") + b"\0MORE"
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_entries(
                Path(directory),
                [
                    {
                        "key": "eboot_00000005",
                        "offset": 5,
                        "original": "予算",
                        "translation": "预算",
                        "context": "test",
                    }
                ],
            )
            with self.assertRaisesRegex(eboot_patch.EbootPatchError, "does not match"):
                eboot_patch.load(source, path)

    def test_rejects_control_mismatch_and_oversized_translation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mismatch = self._write_entries(
                root,
                [
                    {
                        "key": "eboot_00000000",
                        "offset": 0,
                        "original": "武器%s",
                        "translation": "武器",
                        "context": "test",
                    }
                ],
            )
            with self.assertRaisesRegex(eboot_patch.EbootPatchError, "Control sequence"):
                eboot_patch.load_entries(mismatch)

            oversized = self._write_entries(
                root,
                [
                    {
                        "key": "eboot_00000000",
                        "offset": 0,
                        "original": "武器",
                        "translation": "新武器",
                        "context": "test",
                    }
                ],
            )
            patch_set = eboot_patch.load("武器\0".encode("cp932"), oversized)
            with self.assertRaisesRegex(eboot_patch.EbootPatchError, "in-place slot"):
                eboot_patch.replace(patch_set)


class EncodingAndFontTests(unittest.TestCase):
    def test_detects_cp932_and_utf8(self):
        self.assertEqual(decode("日本語".encode("cp932")).encoding, "cp932")
        self.assertEqual(decode("中文".encode("utf-8")).encoding, "utf-8")

    def test_dynamic_font_mapping_is_deterministic(self):
        table = "亜唖娃".encode("utf-16le")
        first = font.build_plan(table, {"确", "认"}, set())
        second = font.build_plan(table, {"认", "确"}, set())
        self.assertEqual(first.mapping_json(), second.mapping_json())
        self.assertEqual(set(first.substitutions), {"确", "认"})

    def test_dynamic_font_mapping_does_not_replace_direct_cp932_glyphs(self):
        table = "亜嗣娃".encode("utf-16le")
        plan = font.build_plan(table, {"骗"}, {"嗣"})
        self.assertNotEqual(plan.substitutions["骗"], "嗣")
        self.assertNotIn("嗣", {mapping.slot for mapping in plan.mappings})

    def test_game_profile_rejects_unsupported_cp932_extensions(self):
        self.assertEqual("增".encode("cp932"), bytes.fromhex("ED81"))
        self.assertEqual("薰".encode("cp932"), bytes.fromhex("EE82"))
        self.assertFalse(is_game_safe_cp932("增"))
        self.assertFalse(is_game_safe_cp932("薰"))
        self.assertEqual(font.required_substitutions(["增薰"]), {"增", "薰"})

    def test_game_profile_keeps_supported_cp932_symbols(self):
        text = "①～－"
        self.assertEqual(text.encode("cp932"), bytes.fromhex("87408160817C"))
        self.assertTrue(all(is_game_safe_cp932(char) for char in text))
        self.assertEqual(font.required_substitutions([text]), set())
        self.assertEqual(decode(text.encode("cp932")).encode(), text.encode("cp932"))

    def test_encodes_unlocked_skill_message_without_unsafe_extensions(self):
        text = "新增技能已解锁"
        required = font.required_substitutions([text])
        self.assertEqual(required, {"增", "锁"})
        plan = font.build_plan("亜唖娃".encode("utf-16le"), required, set())
        substituted = "".join(plan.substitutions.get(char, char) for char in text)
        encoded = encode_game_text(text, plan.substitutions)
        self.assertEqual(encoded, substituted.encode("cp932"))
        self.assertTrue(all(is_game_safe_cp932(char) for char in substituted))
        self.assertNotIn(bytes.fromhex("ED81"), encoded)
        with self.assertRaisesRegex(EncodingError, "Unsafe CP932 byte sequence ED81"):
            encode_game_text(text, {"锁": "亜"})


if __name__ == "__main__":
    unittest.main()
