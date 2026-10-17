import tempfile
import unittest
from pathlib import Path

from auto_subtitle.cli import _display_width, _fit_to_width, _output_stem


class OutputStemTests(unittest.TestCase):
    def test_free_name_is_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "视频.mp4"
            directory, stem = _output_stem(source, tmp, [".srt"], overwrite=False)
            self.assertEqual(directory, Path(tmp))
            self.assertEqual(stem, "视频")

    def test_existing_output_gets_new_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "视频.mp4"
            (Path(tmp) / "视频.srt").write_text("old", encoding="utf-8")
            directory, stem = _output_stem(source, tmp, [".srt"], overwrite=False)
            self.assertEqual(stem, "视频.1")

    def test_checks_all_requested_formats(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "视频.mp4"
            (Path(tmp) / "视频.txt").write_text("old", encoding="utf-8")
            _, stem = _output_stem(source, tmp, [".srt", ".txt"], overwrite=False)
            self.assertEqual(stem, "视频.1")

    def test_overwrite_keeps_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "视频.mp4"
            (Path(tmp) / "视频.srt").write_text("old", encoding="utf-8")
            _, stem = _output_stem(source, tmp, [".srt"], overwrite=True)
            self.assertEqual(stem, "视频")

    def test_creates_output_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "新目录" / "字幕"
            source = Path(tmp) / "视频.mp4"
            directory, _ = _output_stem(source, str(target), [".srt"], overwrite=False)
            self.assertTrue(directory.exists())


class FitWidthTests(unittest.TestCase):
    def test_display_width_counts_cjk_as_two(self):
        self.assertEqual(_display_width("abc"), 3)
        self.assertEqual(_display_width("中文"), 4)
        self.assertEqual(_display_width("a中"), 3)

    def test_short_line_is_padded(self):
        line = _fit_to_width("abc", 6)
        self.assertEqual(line, "abc   ")
        self.assertEqual(_display_width(line), 6)

    def test_long_line_is_truncated_to_limit(self):
        line = _fit_to_width("这是一个很长很长的中文预览内容", 10)
        self.assertEqual(_display_width(line), 10)
        self.assertTrue(line.rstrip().endswith("…"))


if __name__ == "__main__":
    unittest.main()
