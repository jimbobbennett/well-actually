"""Continuously transcribe microphone audio and persist finalized speech segments."""

from __future__ import annotations

import logging
import os
import re
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .audio_capture import build_raw_capture_command
from .led_indicator import LedIndicator, LedIndicatorError
from .pavlok import PavlokClient, PavlokClientError

LOGGER = logging.getLogger("well_actually_processing")
INSERT_SPEECH_LOG_SQL = """
    INSERT INTO public.speech_log ("time", "sid", "content", "ms_score", "zap_sent")
    VALUES (%s, %s, %s, %s, %s)
"""
SESSION_MAX_SECONDS = 30 * 60
RECONNECT_DELAY_SECONDS = 5


class ServiceError(RuntimeError):
    """Raised when a service integration cannot continue."""


@dataclass(frozen=True)
class SpeechLogRecord:
    time: datetime
    sid: int | None
    content: str
    zap_sent: bool = False


def speaker_id_to_number(speaker_id: str | None) -> int | None:
    if speaker_id is None:
        return None
    match = re.fullmatch(r"Guest-(\d+)", speaker_id)
    return int(match.group(1)) if match else None


def contains_well_actually_phrase(text: str) -> bool:
    words = re.findall(r"[^\W_]+", text.casefold())
    return any(
        words[index : index + 2] == ["well", "actually"]
        for index in range(len(words) - 1)
    )


def build_speech_log_record(
    result,
    stream_started_at: datetime,
    zap_sent: bool = False,
) -> SpeechLogRecord | None:
    content = result.text or ""
    if not content.strip():
        return None
    if stream_started_at.tzinfo is None:
        raise ValueError("The audio stream start time must be timezone-aware.")

    offset_ticks = result.offset
    if offset_ticks is None or offset_ticks < 0:
        raise ValueError("Azure Speech returned an invalid audio offset.")

    event_time_utc = stream_started_at.astimezone(timezone.utc) + timedelta(
        microseconds=offset_ticks / 10
    )
    return SpeechLogRecord(
        time=event_time_utc.replace(tzinfo=None),
        sid=speaker_id_to_number(getattr(result, "speaker_id", None)),
        content=content,
        zap_sent=zap_sent,
    )


class SpeechLogStore:
    def __init__(self, connection_string: str) -> None:
        try:
            import psycopg
        except ImportError as exc:
            raise ServiceError(
                "PostgreSQL driver is missing; install the package with the [service] extra."
            ) from exc

        self._psycopg = psycopg
        self._connection_string = connection_string
        self._connection = None
        self._lock = threading.Lock()
        try:
            self._connect()
        except self._psycopg.Error as exc:
            raise ServiceError("Could not connect to the configured TimescaleDB.") from exc
        try:
            self._connection.execute(
                'SELECT "time", "sid", "content", "ms_score", "zap_sent" '
                "FROM public.speech_log WHERE false"
            )
            self._connection.rollback()
        except self._psycopg.Error as exc:
            self.close()
            raise ServiceError("Cannot access public.speech_log with the configured role.") from exc

    def _connect(self) -> None:
        self._connection = self._psycopg.connect(
            self._connection_string,
            connect_timeout=10,
        )

    def insert(self, record: SpeechLogRecord) -> None:
        last_error = None
        with self._lock:
            for attempt in range(3):
                try:
                    if self._connection is None or self._connection.closed:
                        self._connect()
                    self._connection.execute(
                        INSERT_SPEECH_LOG_SQL,
                        (
                            record.time,
                            record.sid,
                            record.content,
                            None,
                            record.zap_sent,
                        ),
                    )
                    self._connection.commit()
                    return
                except self._psycopg.Error as exc:
                    last_error = exc
                    if self._connection is not None:
                        self._connection.close()
                        self._connection = None
                    if attempt < 2:
                        time.sleep(2**attempt)
        raise ServiceError(
            "Failed to write a finalized segment to speech_log after 3 attempts."
        ) from last_error

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None


def _load_speech_sdk():
    try:
        import azure.cognitiveservices.speech as speechsdk
    except ImportError as exc:
        raise ServiceError(
            "Azure Speech SDK is missing; install the package with the [service] extra."
        ) from exc
    return speechsdk


def _required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ServiceError(f"Required environment variable {name} is not set.")
    return value


def _run_transcription_session(
    speechsdk,
    store: SpeechLogStore,
    stop_event: threading.Event,
    led_indicator: LedIndicator,
    pavlok_client: PavlokClient | None,
) -> None:
    device = os.environ.get("WELL_ACTUALLY_AUDIO_DEVICE", "hw:CARD=M0,DEV=0")
    sample_rate = 16_000
    channels = 1
    speech_config = speechsdk.SpeechConfig(
        subscription=_required_environment("AZURE_SPEECH_KEY"),
        endpoint=_required_environment("AZURE_SPEECH_ENDPOINT"),
    )
    speech_config.speech_recognition_language = os.environ.get(
        "AZURE_SPEECH_LANGUAGE", "en-US"
    )
    audio_format = speechsdk.audio.AudioStreamFormat(
        samples_per_second=sample_rate,
        bits_per_sample=16,
        channels=channels,
    )
    push_stream = speechsdk.audio.PushAudioInputStream(stream_format=audio_format)
    audio_config = speechsdk.audio.AudioConfig(stream=push_stream)
    transcriber = speechsdk.transcription.ConversationTranscriber(
        speech_config=speech_config,
        audio_config=audio_config,
    )

    session_stopped = threading.Event()
    session_failed = threading.Event()
    session_errors: list[str] = []
    stream_started_at: list[datetime | None] = [None]

    def on_transcribed(event) -> None:
        result = event.result
        if result.reason != speechsdk.ResultReason.RecognizedSpeech:
            return
        zap_sent = False
        if contains_well_actually_phrase(result.text or ""):
            zap_sent = _on_well_actually_detected(led_indicator, pavlok_client)
        try:
            origin = stream_started_at[0]
            if origin is None:
                raise ServiceError("Speech arrived before the audio stream was initialized.")
            record = build_speech_log_record(result, origin, zap_sent=zap_sent)
            if record is None:
                return
            store.insert(record)
            LOGGER.info("Stored speech_log segment: sid=%s time=%s", record.sid, record.time)
        except (ServiceError, ValueError) as exc:
            session_errors.append(str(exc))
            session_failed.set()
            LOGGER.exception("Could not persist a finalized speech segment.")

    def on_canceled(event) -> None:
        details = speechsdk.CancellationDetails(event.result)
        message = f"reason={details.reason}, error_code={details.error_code}"
        if details.error_details:
            message += f": {details.error_details}"
        session_errors.append(message)
        session_failed.set()
        LOGGER.error("Azure Speech canceled the transcription session: %s", message)

    def on_session_stopped(_event) -> None:
        session_stopped.set()

    transcriber.transcribed.connect(on_transcribed)
    transcriber.canceled.connect(on_canceled)
    transcriber.session_stopped.connect(on_session_stopped)

    process: subprocess.Popen[bytes] | None = None
    started = False
    try:
        transcriber.start_transcribing_async().get()
        started = True
        process = subprocess.Popen(
            build_raw_capture_command(
                device=device,
                sample_rate=sample_rate,
                channels=channels,
            ),
            stdout=subprocess.PIPE,
            bufsize=0,
        )
        if process.stdout is None:
            raise ServiceError("Could not read PCM from arecord.")
        stream_started_at[0] = datetime.now(timezone.utc)
        LOGGER.info("Recording and streaming from %s.", device)
        session_deadline = time.monotonic() + SESSION_MAX_SECONDS

        while (
            not stop_event.is_set()
            and not session_failed.is_set()
            and time.monotonic() < session_deadline
        ):
            chunk = process.stdout.read(3_200)
            if chunk:
                push_stream.write(chunk)
                continue

            return_code = process.poll()
            if return_code is not None:
                if return_code != 0:
                    raise ServiceError(f"arecord exited with code {return_code}.")
                break

        if session_errors:
            raise ServiceError(session_errors[-1])
    except OSError as exc:
        raise ServiceError(f"Could not start or read from arecord: {exc}") from exc
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if process is not None and process.stdout is not None:
            process.stdout.close()
        push_stream.close()
        if started:
            transcriber.stop_transcribing_async().get()
            session_stopped.wait(timeout=10)

    if session_errors:
        raise ServiceError(session_errors[-1])


def _on_well_actually_detected(
    led_indicator: LedIndicator,
    pavlok_client: PavlokClient | None = None,
) -> bool:
    LOGGER.info("Recognized phrase 'Well actually'; requesting a 5-second lightning bolt.")
    try:
        led_indicator.show_phrase_detected()
    except LedIndicatorError:
        LOGGER.exception("Could not signal the LED matrix after phrase recognition.")
    if pavlok_client is None:
        return False
    try:
        pavlok_client.send_stimulus()
        LOGGER.info("Sent Pavlok stimulus after phrase recognition.")
        return True
    except PavlokClientError:
        LOGGER.exception("Could not send the Pavlok stimulus.")
        return False


def run_service(stop_event: threading.Event) -> None:
    speechsdk = _load_speech_sdk()
    try:
        pavlok_client = PavlokClient.from_environment()
    except ValueError as exc:
        raise ServiceError(f"Invalid Pavlok configuration: {exc}") from exc
    if pavlok_client is None:
        LOGGER.warning(
            "Pavlok integration is disabled; set WAKE_WORD_API_TOKEN to enable it."
        )
    led_indicator = LedIndicator(
        os.environ.get(
            "WELL_ACTUALLY_LED_SOCKET",
            "unoq-led-indicator/well-actually-led.sock",
        )
    )
    store = SpeechLogStore(_required_environment("TIMESCALEDB_URL"))
    try:
        while not stop_event.is_set():
            try:
                _run_transcription_session(
                    speechsdk,
                    store,
                    stop_event,
                    led_indicator,
                    pavlok_client,
                )
            except Exception:
                if stop_event.is_set():
                    break
                LOGGER.exception(
                    "Speech session failed; reconnecting in %s seconds.",
                    RECONNECT_DELAY_SECONDS,
                )
                stop_event.wait(RECONNECT_DELAY_SECONDS)
            else:
                if not stop_event.is_set():
                    LOGGER.info("Speech session ended; starting a fresh session.")
                    stop_event.wait(1)
    finally:
        store.close()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    stop_event = threading.Event()
    signal.signal(signal.SIGINT, lambda _signal, _frame: stop_event.set())
    signal.signal(signal.SIGTERM, lambda _signal, _frame: stop_event.set())
    try:
        run_service(stop_event)
    except ServiceError as exc:
        LOGGER.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
