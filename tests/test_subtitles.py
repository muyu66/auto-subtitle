import unittest
from types import SimpleNamespace

from auto_subtitle.subtitles import (
    Cue,
    SENTENCE_END,
    _split_after,
    _split_long,
    apply_replacements,
    build_cues,
    clean_text,
    cues_to_srt,
    cues_to_text,
    format_timestamp,
    parse_replacements,
)


class TimestampTests(unittest.TestCase):
    def test_format_timestamp(self):
        self.assertEqual(format_timestamp(0), "00:00:00,000")
        self.assertEqual(format_timestamp(1.5), "00:00:01,500")
        self.assertEqual(format_timestamp(3661.234), "01:01:01,234")
        self.assertEqual(format_timestamp(-3), "00:00:00,000")


class CleanTextTests(unittest.TestCase):
    def test_removes_spaces_between_chinese_characters(self):
        self.assertEqual(clean_text("你 好 世 界"), "你好世界")

    def test_keeps_spaces_between_english_words(self):
        self.assertEqual(clean_text("Hello  world"), "Hello world")

    def test_keeps_space_between_chinese_and_english(self):
        self.assertEqual(clean_text("使用 Python 开发"), "使用 Python 开发")


class SplitTests(unittest.TestCase):
    def test_sentence_split_keeps_closing_quote(self):
        text = "他说：“你好。”然后走了。再见。"
        self.assertEqual(
            _split_after(text, SENTENCE_END),
            ["他说：“你好。”", "然后走了。", "再见。"],
        )

    def test_long_text_is_always_within_limit(self):
        text = "这是一个没有任何标点符号的非常长的句子" * 5
        pieces = _split_long(text, 15)
        self.assertTrue(pieces)
        self.assertTrue(all(len(piece) <= 15 for piece in pieces))
        self.assertEqual("".join(pieces), text)

    def test_english_breaks_at_spaces(self):
        text = "This is a rather long English sentence that should wrap nicely."
        pieces = _split_long(text, 24)
        self.assertTrue(all(len(piece) <= 24 for piece in pieces))
        self.assertTrue(all("  " not in piece for piece in pieces))


class BuildCueTests(unittest.TestCase):
    def test_splits_sentences_with_proportional_timing(self):
        segments = [
            SimpleNamespace(start=0.0, end=10.0, text="第一句话。第二句话。"),
        ]
        cues = build_cues(segments, max_chars=30)
        self.assertEqual([cue.text for cue in cues], ["第一句话。", "第二句话。"])
        self.assertAlmostEqual(cues[0].start, 0.0)
        self.assertAlmostEqual(cues[0].end, 5.0, delta=0.01)
        self.assertAlmostEqual(cues[1].start, 5.0, delta=0.01)
        self.assertAlmostEqual(cues[1].end, 10.0)

    def test_skips_non_speech(self):
        segments = [SimpleNamespace(start=0.0, end=2.0, text="♪ ♪")]
        self.assertEqual(build_cues(segments), [])

    def test_cues_do_not_overlap(self):
        segments = [
            SimpleNamespace(start=0.0, end=5.0, text="第一段。"),
            SimpleNamespace(start=3.0, end=8.0, text="第二段。"),
        ]
        cues = build_cues(segments)
        self.assertEqual(len(cues), 2)
        self.assertGreaterEqual(cues[1].start, cues[0].end)

    def test_zero_duration_segment_gets_valid_end(self):
        segments = [SimpleNamespace(start=2.0, end=2.0, text="你好。")]
        cues = build_cues(segments)
        self.assertEqual(len(cues), 1)
        self.assertGreater(cues[0].end, cues[0].start)


class ReplacementTests(unittest.TestCase):
    def test_parse_and_apply(self):
        mapping = parse_replacements("雷阶=连接，换蛋=换弹;C4=炸弹")
        self.assertEqual(
            mapping, {"雷阶": "连接", "换蛋": "换弹", "C4": "炸弹"}
        )
        cues = [Cue(0, 1, "雷阶断开了，换蛋"), Cue(1, 2, "放置 C4")]
        apply_replacements(cues, mapping)
        self.assertEqual(cues[0].text, "连接断开了，换弹")
        self.assertEqual(cues[1].text, "放置 炸弹")

    def test_invalid_entries_ignored(self):
        self.assertEqual(parse_replacements(None), {})
        self.assertEqual(parse_replacements("没有等号,=空, 旧=新"), {"旧": "新"})


class ExportTests(unittest.TestCase):
    def test_srt_format(self):
        srt = cues_to_srt([Cue(0.0, 1.5, "你好"), Cue(2.0, 3.25, "世界")])
        self.assertEqual(
            srt,
            "1\n00:00:00,000 --> 00:00:01,500\n你好\n\n"
            "2\n00:00:02,000 --> 00:00:03,250\n世界\n",
        )

    def test_text_format(self):
        self.assertEqual(cues_to_text([Cue(0, 1, "你好"), Cue(1, 2, "世界")]), "你好\n世界\n")


if __name__ == "__main__":
    unittest.main()
