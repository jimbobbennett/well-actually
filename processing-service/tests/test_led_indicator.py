import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from well_actually_processing.led_indicator import (
    DEFAULT_LED_SOCKET,
    PHRASE_DETECTED_LED_MESSAGE,
    LedIndicator,
    LedIndicatorError,
)


class LedIndicatorTests(unittest.TestCase):
    @patch("well_actually_processing.led_indicator.socket.socket")
    def test_default_socket_is_in_the_shared_app_directory(self, socket_factory):
        LedIndicator().show_phrase_detected()

        socket_factory.return_value.__enter__.return_value.sendto.assert_called_once_with(
            PHRASE_DETECTED_LED_MESSAGE,
            DEFAULT_LED_SOCKET,
        )

    @patch("well_actually_processing.led_indicator.socket.socket")
    def test_sends_phrase_event_to_local_socket(self, socket_factory):
        indicator = LedIndicator("/tmp/test-led.sock")
        indicator.show_phrase_detected()

        socket_factory.assert_called_once()
        socket_factory.return_value.__enter__.return_value.sendto.assert_called_once_with(
            PHRASE_DETECTED_LED_MESSAGE,
            "/tmp/test-led.sock",
        )

    def test_sends_datagram_to_local_receiver(self):
        with tempfile.TemporaryDirectory() as directory:
            socket_path = Path(directory) / "indicator.sock"
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as receiver:
                receiver.bind(str(socket_path))
                receiver.settimeout(1)

                LedIndicator(str(socket_path)).show_phrase_detected()

                self.assertEqual(receiver.recv(64), PHRASE_DETECTED_LED_MESSAGE)

    def test_unavailable_socket_is_reported(self):
        with self.assertRaisesRegex(LedIndicatorError, "LED app"):
            LedIndicator("/path/that/does/not/exist/socket").show_phrase_detected()


if __name__ == "__main__":
    unittest.main()
