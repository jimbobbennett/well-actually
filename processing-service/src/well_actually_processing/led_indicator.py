"""Send recognized-phrase notifications to the Arduino App Lab LED app."""

from __future__ import annotations

import logging
import socket

LOGGER = logging.getLogger("well_actually_processing.led_indicator")
DEFAULT_LED_SOCKET = "unoq-led-indicator/well-actually-led.sock"
PHRASE_DETECTED_LED_MESSAGE = b"phrase-detected"


class LedIndicatorError(RuntimeError):
    """Raised when the LED indicator app cannot be reached."""


class LedIndicator:
    def __init__(self, socket_path: str = DEFAULT_LED_SOCKET) -> None:
        self._socket_path = socket_path

    def show_phrase_detected(self) -> None:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
                client.sendto(PHRASE_DETECTED_LED_MESSAGE, self._socket_path)
        except OSError as exc:
            raise LedIndicatorError(
                f"Could not send a phrase-detected event to the LED app at {self._socket_path}."
            ) from exc
        LOGGER.info("Sent phrase-detected event to LED app socket %s.", self._socket_path)
