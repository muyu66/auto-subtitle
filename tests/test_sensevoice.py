import unittest

from auto_subtitle.sensevoice import _meaningful


class MeaningfulTextTests(unittest.TestCase):
    def test_filters_punctuation_and_single_chars(self):
        self.assertFalse(_meaningful(""))
        self.assertFalse(_meaningful("。！？"))
        self.assertFalse(_meaningful("这。"))
        self.assertTrue(_meaningful("走啊"))
        self.assertTrue(_meaningful("C4"))
        self.assertTrue(_meaningful("OK"))


if __name__ == "__main__":
    unittest.main()
