import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from auto_subtitle.model_store import (
    _format_size,
    cache_root,
    canonical_model_name,
    is_model_ready,
    is_sensevoice_ready,
    model_directory,
    sensevoice_directory,
)


class ModelNameTests(unittest.TestCase):
    def test_aliases(self):
        self.assertEqual(canonical_model_name("large-v3-turbo"), "turbo")
        self.assertEqual(canonical_model_name("large-turbo"), "turbo")
        self.assertEqual(canonical_model_name("large"), "large-v3")
        self.assertEqual(canonical_model_name("small"), "small")

    def test_format_size(self):
        self.assertEqual(_format_size(75 * 1024 * 1024), "75.0 MB")
        self.assertEqual(_format_size(2 * 1024 ** 3), "2.00 GB")


class CacheTests(unittest.TestCase):
    def test_cache_root_uses_localappdata(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"LOCALAPPDATA": tmp}):
                self.assertEqual(
                    cache_root(), Path(tmp) / "auto-subtitle" / "models"
                )
                self.assertEqual(
                    model_directory("turbo"), Path(tmp) / "auto-subtitle"
                    / "models" / "turbo"
                )

    def test_legacy_cache_is_migrated(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "video-quick-edit" / "models" / "turbo"
            legacy.mkdir(parents=True)
            (legacy / "model.bin").write_bytes(b"x")
            with patch.dict(os.environ, {"LOCALAPPDATA": tmp}):
                root = cache_root()
                self.assertEqual(root, Path(tmp) / "auto-subtitle" / "models")
                self.assertTrue((root / "turbo" / "model.bin").is_file())
                self.assertFalse(legacy.parent.exists())

    def test_model_ready_requires_marker_and_model_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"LOCALAPPDATA": tmp}):
                directory = model_directory("turbo")
                self.assertFalse(is_model_ready("turbo"))
                directory.mkdir(parents=True)
                (directory / ".complete").write_text("ok", encoding="utf-8")
                self.assertFalse(is_model_ready("turbo"))
                (directory / "model.bin").write_bytes(b"x")
                self.assertTrue(is_model_ready("turbo"))

    def test_sensevoice_ready_checks_marker_and_file_sizes(self):
        files = (("model.int8.onnx", 2), ("tokens.txt", 3))
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"LOCALAPPDATA": tmp}):
                with patch(
                    "auto_subtitle.model_store.SENSEVOICE_FILES", files
                ):
                    directory = sensevoice_directory()
                    self.assertFalse(is_sensevoice_ready())
                    directory.mkdir(parents=True)
                    (directory / "model.int8.onnx").write_bytes(b"xx")
                    self.assertFalse(is_sensevoice_ready())
                    (directory / "tokens.txt").write_bytes(b"abc")
                    (directory / ".complete").write_text("ok", encoding="utf-8")
                    self.assertTrue(is_sensevoice_ready())
                    # 文件被截断后应重新下载
                    (directory / "tokens.txt").write_bytes(b"a")
                    self.assertFalse(is_sensevoice_ready())


if __name__ == "__main__":
    unittest.main()
