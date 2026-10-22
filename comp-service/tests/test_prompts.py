import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from speech_coach.llm import Decision
from speech_coach.prompts import load_prompt


class ManagedPromptTests(unittest.TestCase):
    def setUp(self):
        self.settings = SimpleNamespace(
            arize_api_key="test-key", arize_prompt_id="prompt/id=",
            arize_prompt_label="", testing_mode=True,
        )
        self.version = {
            "id": "version-1", "input_variable_format": "F_STRING",
            "messages": [
                {"role": "SYSTEM", "content": 'Return {{"condescending": boolean}}.'},
                {"role": "USER", "content": "{conversation_json}"},
            ],
        }

    def load(self, version=None, status=200):
        def handler(request):
            self.request = request
            return httpx.Response(status, json=version if version is not None else self.version)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        with patch("speech_coach.prompts.httpx.Client", return_value=client):
            return load_prompt(self.settings)

    def test_render_preserves_json_and_untrusted_braces(self):
        prompt = self.load()
        transcript = '{"current_turn": "{conversation_json.__class__}"}'
        messages = prompt.render(transcript)
        self.assertEqual(messages[0]["content"], 'Return {"condescending": boolean}.')
        self.assertEqual(messages[1]["content"], transcript)
        self.assertEqual(prompt.version_id, "version-1")
        self.assertEqual(prompt.label, "staging")
        self.assertIn("prompt%2Fid%3D/labels/staging", self.request.url.raw_path.decode())

    def test_production_and_override_labels(self):
        self.settings.testing_mode = False
        self.assertEqual(self.load().label, "production")
        self.settings.arize_prompt_label = "candidate"
        self.assertEqual(self.load().label, "candidate")

    def test_rejects_invalid_templates(self):
        for content in ("{conversation_json.__class__}", "{other}",
                        "{conversation_json!r}", "{conversation_json:>20}", "{", "no input"):
            with self.subTest(content=content):
                version = copy.deepcopy(self.version)
                version["messages"][1]["content"] = content
                with self.assertRaises(ValueError):
                    self.load(version)

    def test_http_error_stops_loading(self):
        with self.assertRaises(httpx.HTTPStatusError):
            self.load(status=403)

    def test_strict_decision_validation(self):
        self.assertTrue(Decision.parse(
            '{"condescending": true, "reexplaining": false, "confidence": 0.9}'
        ).triggers(0.85))
        with self.assertRaises(ValueError):
            Decision.parse('{"condescending": "true", "reexplaining": false, "confidence": 0.9}')

    def test_tone_assessment_and_legacy_responses(self):
        result = Decision.parse(
            '{"tone":"patronizing", "tone_evidence":["let me explain slowly"],'
            '"condescending":true,"reexplaining":false,"confidence":0.9}')
        self.assertEqual(result.tone, "patronizing")
        self.assertEqual(result.tone_evidence, ["let me explain slowly"])
        self.assertTrue(result.triggers(0.85))
        self.assertIsNone(Decision.parse(
            '{"condescending":false,"reexplaining":false,"confidence":0.2}'
        ).tone)

    def test_tone_schema_rejects_invalid_or_partial_fields(self):
        import json
        base = {"condescending": True, "reexplaining": False, "confidence": 0.9}
        for fields in ({"tone": "patronizing"},
                       {"tone": "", "tone_evidence": []},
                       {"tone": 1, "tone_evidence": []},
                       {"tone": "neutral", "tone_evidence": "unsupported"},
                       {"tone": "neutral", "tone_evidence": [False]},
                       {"tone": "neutral", "tone_evidence": ["cue"] * 6}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                Decision.parse(json.dumps({**base, **fields}))


if __name__ == "__main__":
    unittest.main()
