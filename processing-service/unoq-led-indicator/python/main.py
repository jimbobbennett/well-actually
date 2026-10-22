"""Receive recognized-phrase notifications and forward them to the LED sketch."""

import atexit
import os
import socket
from pathlib import Path

from arduino.app_utils import App, Bridge

SOCKET_PATH = Path(
    os.environ.get(
        "WELL_ACTUALLY_LED_SOCKET",
        str(Path(__file__).resolve().parents[1] / "well-actually-led.sock"),
    )
)
PHRASE_DETECTED_LED_MESSAGE = b"phrase-detected"

SOCKET_PATH.unlink(missing_ok=True)
receiver = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
receiver.bind(str(SOCKET_PATH))
receiver.settimeout(0.1)


def close_receiver() -> None:
    receiver.close()
    SOCKET_PATH.unlink(missing_ok=True)


def loop() -> None:
    try:
        message = receiver.recv(64)
    except TimeoutError:
        return
    if message == PHRASE_DETECTED_LED_MESSAGE:
        print("Recognized-phrase event received; requesting lightning bolt.", flush=True)
        try:
            acknowledged = Bridge.call("show_lightning_bolt", timeout=5)
        except (ConnectionError, TimeoutError, RuntimeError, ValueError) as exc:
            print(f"Microcontroller did not accept the LED request: {exc}", flush=True)
            return
        if acknowledged is not True:
            print(
                f"Microcontroller returned an unexpected LED acknowledgement: {acknowledged!r}",
                flush=True,
            )
            return
        print("Microcontroller accepted the lightning-bolt request.", flush=True)


atexit.register(close_receiver)
App.run(user_loop=loop)
