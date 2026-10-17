import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from auto_subtitle.asr import DEFAULT_MODEL
from auto_subtitle.catalog import (
    MODEL_CHOICES,
    apply_choice,
    current_choice_key,
    current_choice_label,
)
from auto_subtitle.cli import choose_model


def _args(engine="auto", model=DEFAULT_MODEL):
    return SimpleNamespace(engine=engine, model=model)


class CatalogTests(unittest.TestCase):
    def test_choices_are_unique_and_valid(self):
        keys = [choice.key for choice in MODEL_CHOICES]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all(choice.engine in ("whisper", "sensevoice") for choice in MODEL_CHOICES))

    def test_current_choice_from_auto(self):
        self.assertEqual(current_choice_key("auto", DEFAULT_MODEL), "turbo")
        self.assertEqual(current_choice_key("whisper", "large-v3"), "large-v3")

    def test_apply_choice(self):
        args = _args()
        apply_choice(args, "sensevoice")
        self.assertEqual((args.engine, args.model), ("sensevoice", DEFAULT_MODEL))

        apply_choice(args, "small")
        self.assertEqual((args.engine, args.model), ("whisper", "small"))

        apply_choice(args, "my/model", model="my/model")
        self.assertEqual((args.engine, args.model), ("whisper", "my/model"))

    def test_label_for_custom_model(self):
        self.assertEqual(
            current_choice_label("whisper", "my/model"),
            "Whisper（my/model）",
        )


class ChooseModelTests(unittest.TestCase):
    def _choose(self, args, inputs):
        with redirect_stdout(io.StringIO()), patch(
            "builtins.input", side_effect=inputs
        ):
            choose_model(args)

    def test_enter_keeps_current(self):
        args = _args()
        self._choose(args, [""])
        self.assertEqual((args.engine, args.model), ("auto", DEFAULT_MODEL))

    def test_number_selects_model(self):
        args = _args()
        self._choose(args, ["3"])  # Whisper large-v3
        self.assertEqual((args.engine, args.model), ("whisper", "large-v3"))

    def test_custom_whisper_model(self):
        args = _args()
        self._choose(args, [str(len(MODEL_CHOICES) + 1), "my/model"])
        self.assertEqual((args.engine, args.model), ("whisper", "my/model"))

    def test_invalid_number_reprompts(self):
        args = _args()
        self._choose(args, ["99", "2"])
        self.assertEqual((args.engine, args.model), ("whisper", "turbo"))


if __name__ == "__main__":
    unittest.main()
