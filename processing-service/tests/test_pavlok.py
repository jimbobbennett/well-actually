import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from well_actually_processing.pavlok import (
    ALLOWED_STIMULUS_TYPES,
    DEFAULT_PAVLOK_API_URL,
    DEFAULT_STIMULUS_LEVEL,
    DEFAULT_STIMULUS_TYPE,
    MAX_STIMULUS_LEVEL,
    MIN_STIMULUS_LEVEL,
    REQUEST_TIMEOUT_SECONDS,
    PavlokClient,
    PavlokClientError,
)


class PavlokClientTests(unittest.TestCase):
    @patch("well_actually_processing.pavlok.urlopen")
    def test_sends_default_beep_request(self, urlopen):
        urlopen.return_value.__enter__.return_value = SimpleNamespace(status=200)

        PavlokClient("test-token").send_stimulus()

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, DEFAULT_PAVLOK_API_URL)
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.get_header("Authorization"), "test-token")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(
            json.loads(request.data),
            {
                "stimulus": {
                    "stimulusType": DEFAULT_STIMULUS_TYPE,
                    "stimulusValue": DEFAULT_STIMULUS_LEVEL,
                }
            },
        )
        self.assertEqual(
            urlopen.call_args.kwargs["timeout"],
            REQUEST_TIMEOUT_SECONDS,
        )

    @patch("well_actually_processing.pavlok.urlopen")
    def test_uses_configured_url_and_timeout(self, urlopen):
        urlopen.return_value.__enter__.return_value = SimpleNamespace(status=202)

        PavlokClient(
            "test-token",
            api_url="https://pavlok.example.test/send",
            timeout=2,
            stimulus_type="zap",
            stimulus_level=MAX_STIMULUS_LEVEL,
        ).send_stimulus()

        self.assertEqual(
            urlopen.call_args.args[0].full_url,
            "https://pavlok.example.test/send",
        )
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 2)
        self.assertEqual(
            json.loads(urlopen.call_args.args[0].data)["stimulus"],
            {"stimulusType": "zap", "stimulusValue": MAX_STIMULUS_LEVEL},
        )

    @patch("well_actually_processing.pavlok.urlopen")
    def test_supports_every_documented_stimulus_type(self, urlopen):
        urlopen.return_value.__enter__.return_value = SimpleNamespace(status=200)

        for stimulus_type in ALLOWED_STIMULUS_TYPES:
            with self.subTest(stimulus_type=stimulus_type):
                PavlokClient(
                    "test-token",
                    stimulus_type=stimulus_type,
                    stimulus_level=MIN_STIMULUS_LEVEL,
                ).send_stimulus()
                self.assertEqual(
                    json.loads(urlopen.call_args.args[0].data)["stimulus"],
                    {
                        "stimulusType": stimulus_type,
                        "stimulusValue": MIN_STIMULUS_LEVEL,
                    },
                )

    @patch("well_actually_processing.pavlok.urlopen")
    def test_reports_http_errors_without_exposing_token(self, urlopen):
        urlopen.side_effect = HTTPError(
            DEFAULT_PAVLOK_API_URL,
            401,
            "Unauthorized",
            {},
            None,
        )

        with self.assertRaisesRegex(PavlokClientError, "HTTP 401") as error:
            PavlokClient("secret-token").send_stimulus()

        self.assertNotIn("secret-token", str(error.exception))

    @patch("well_actually_processing.pavlok.urlopen")
    def test_reports_network_errors(self, urlopen):
        urlopen.side_effect = URLError("connection refused")

        with self.assertRaisesRegex(PavlokClientError, "Could not reach"):
            PavlokClient("secret-token").send_stimulus()

    def test_requires_a_token_and_https_endpoint(self):
        with self.assertRaisesRegex(ValueError, "token is required"):
            PavlokClient(" ")
        with self.assertRaisesRegex(ValueError, "must use HTTPS"):
            PavlokClient("test-token", api_url="http://example.test/send")
        with self.assertRaisesRegex(ValueError, "stimulus type"):
            PavlokClient("test-token", stimulus_type="shock")
        with self.assertRaisesRegex(ValueError, "between 1 and 100"):
            PavlokClient("test-token", stimulus_level=0)
        with self.assertRaisesRegex(ValueError, "between 1 and 100"):
            PavlokClient("test-token", stimulus_level=101)

    @patch.dict("os.environ", {}, clear=True)
    def test_environment_configuration_is_optional(self):
        self.assertIsNone(PavlokClient.from_environment())

    @patch.dict(
        "os.environ",
        {
            "WAKE_WORD_API_TOKEN": "test-token",
            "WAKE_WORD_API_URL": "https://pavlok.example.test/send",
            "PAVLOK_STIMULUS_TYPE": "vibe",
            "PAVLOK_STIMULUS_LEVEL": "1",
        },
        clear=True,
    )
    def test_reads_environment_configuration(self):
        client = PavlokClient.from_environment()

        self.assertIsNotNone(client)
        self.assertEqual(client._api_url, "https://pavlok.example.test/send")
        self.assertEqual(client._stimulus_type, "vibe")
        self.assertEqual(client._stimulus_level, 1)

    @patch.dict(
        "os.environ",
        {
            "WAKE_WORD_API_TOKEN": "replace-with-pavlok-api-token",
            "PAVLOCK_API_KEY": "configured-token",
            "WAKE_WORD_API_URL": "replace-after-api-contract-is-provided",
        },
        clear=True,
    )
    def test_uses_configured_api_key_alias_when_placeholder_is_present(self):
        client = PavlokClient.from_environment()

        self.assertIsNotNone(client)
        self.assertEqual(client._token, "configured-token")
        self.assertEqual(client._api_url, DEFAULT_PAVLOK_API_URL)


if __name__ == "__main__":
    unittest.main()
