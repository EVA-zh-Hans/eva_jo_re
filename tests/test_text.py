import json
import tempfile
import unittest
from pathlib import Path, PurePosixPath

from app import font, nut, paratranz, xml
from app.encoding import decode


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
        self.assertIn('text="中文&amp;值"', rendered)
        self.assertIn(">正文</R>", rendered)
        self.assertIn("<!--壊れたコメント->", rendered)

    def test_reports_nonstandard_xml_without_blocking_scan(self):
        source = "<ROOT><!--bad-><VALUE>日本語</VALUE></ROOT>"
        self.assertIsNotNone(xml.validation_error(source))
        self.assertEqual(len(xml.scan(source)), 1)


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


if __name__ == "__main__":
    unittest.main()
