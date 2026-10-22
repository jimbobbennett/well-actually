import os
import unittest
from unittest.mock import patch

from speech_coach.config import Settings


class PromptSelectionTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "WEARER_OPTED_IN": "true",
            "DATABASE_URL": "postgresql://example/db",
            "OPENAI_BASE_URL": "https://example.com/v1",
            "OPENAI_MODEL": "test-model",
            "OPENAI_API_KEY": "test-key",
            "PAVLOK_AUTHORIZATION": "test-authorization",
            "ARIZE_API_KEY": "test-arize-key",
            "ARIZE_PROMPT_ID_ORIGINAL": "original-id",
            "ARIZE_PROMPT_ID_SENSITIVE": "sensitive-id",
            # A stale exported value must not override the selector.
            "ARIZE_PROMPT_ID": "legacy-id",
        }

    def test_modes_select_matching_id_without_changing_confidence(self):
        for mode in ("original", "sensitive"):
            for testing in ("true", "false"):
                with self.subTest(mode=mode, testing=testing), patch.dict(
                    os.environ, {**self.env, "ARIZE_PROMPT_MODE": mode,
                                 "TESTING_MODE": testing}, clear=True
                ):
                    settings = Settings.from_env()
                    self.assertEqual(settings.arize_prompt_id, f"{mode}-id")
                    self.assertEqual(settings.confidence, 0.85)

    def test_default_mode_is_sensitive(self):
        with patch.dict(os.environ, self.env, clear=True):
            self.assertEqual(Settings.from_env().arize_prompt_id, "sensitive-id")

    def test_stimulus_type_from_environment(self):
        for stimulus in ("beep", "vibe"):
            with self.subTest(stimulus=stimulus), patch.dict(
                os.environ, {**self.env, "PAVLOK_STIMULUS_TYPE": stimulus}, clear=True
            ):
                self.assertEqual(Settings.from_env().stimulus_type, stimulus)

    def test_default_and_empty_stimulus_type(self):
        with patch.dict(os.environ, self.env, clear=True):
            self.assertEqual(Settings.from_env().stimulus_type, "beep")
        with patch.dict(os.environ, {**self.env, "PAVLOK_STIMULUS_TYPE": "  "}, clear=True):
            with self.assertRaisesRegex(ValueError, "PAVLOK_STIMULUS_TYPE"):
                Settings.from_env()

    def test_invalid_mode_is_rejected(self):
        with patch.dict(os.environ, {**self.env, "ARIZE_PROMPT_MODE": "invalid"}, clear=True):
            with self.assertRaisesRegex(ValueError, "ARIZE_PROMPT_MODE"):
                Settings.from_env()

    def test_missing_selected_id_is_rejected(self):
        for value in ("", "   "):
            with patch.dict(os.environ, {**self.env, "ARIZE_PROMPT_ID_SENSITIVE": value}, clear=True):
                with self.assertRaisesRegex(ValueError, "ARIZE_PROMPT_ID_SENSITIVE"):
                    Settings.from_env()


if __name__ == "__main__":
    unittest.main()
