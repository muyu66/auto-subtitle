import unittest
from pathlib import Path

from auto_subtitle.media import (
    format_duration_cn,
    format_hms,
    normalize_path,
    parse_dropped_paths,
)


class ParseDroppedPathsTests(unittest.TestCase):
    def test_single_quoted_path_with_spaces(self):
        self.assertEqual(
            parse_dropped_paths('"C:\\Users\\me\\Videos\\my clip.mp4"'),
            ["C:\\Users\\me\\Videos\\my clip.mp4"],
        )

    def test_multiple_quoted_paths(self):
        self.assertEqual(
            parse_dropped_paths('"C:\\a b\\one.mp4" "C:\\two.mp4"'),
            ["C:\\a b\\one.mp4", "C:\\two.mp4"],
        )

    def test_unquoted_path_with_spaces(self):
        self.assertEqual(
            parse_dropped_paths("C:\\Users\\me\\my clip.mp4"),
            ["C:\\Users\\me\\my clip.mp4"],
        )

    def test_powershell_ampersand_prefix(self):
        self.assertEqual(
            parse_dropped_paths('& "C:\\videos\\a.mp4"'),
            ["C:\\videos\\a.mp4"],
        )

    def test_mixed_quoted_and_unquoted_paths(self):
        self.assertEqual(
            parse_dropped_paths('"C:\\a b\\one.mp4" C:\\two.mp4'),
            ["C:\\a b\\one.mp4", "C:\\two.mp4"],
        )

    def test_single_quoted_path(self):
        self.assertEqual(
            parse_dropped_paths("'C:\\a b\\one.mp4'"),
            ["C:\\a b\\one.mp4"],
        )

    def test_empty_input(self):
        self.assertEqual(parse_dropped_paths("   "), [])

    def test_normalize_path_strips_quotes(self):
        self.assertEqual(normalize_path('"C:\\videos\\a.mp4"'), Path("C:\\videos\\a.mp4"))


class FormatTests(unittest.TestCase):
    def test_format_hms(self):
        self.assertEqual(format_hms(0), "00:00")
        self.assertEqual(format_hms(65), "01:05")
        self.assertEqual(format_hms(3665), "1:01:05")
        self.assertEqual(format_hms(None), "--:--")

    def test_format_duration_cn(self):
        self.assertEqual(format_duration_cn(42), "42 秒")
        self.assertEqual(format_duration_cn(125), "2 分 5 秒")
        self.assertEqual(format_duration_cn(3725), "1 小时 2 分")


if __name__ == "__main__":
    unittest.main()
