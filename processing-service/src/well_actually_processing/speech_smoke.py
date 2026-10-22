"""Stream microphone PCM to Azure Speech and print finalized diarized segments."""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from dataclasses import dataclass

from .audio_capture import build_raw_capture_command


class SpeechSmokeError(RuntimeError):
    """Raised when the live Speech SDK test cannot run."""


@dataclass(frozen=True)
class SmokeTestConfig:
    device: str = "hw:CARD=M0,DEV=0"
    duration_seconds: int = 30
    sample_rate: int = 16_000
    channels: int = 1


def run_smoke_test(config: SmokeTestConfig) -> int:
    try:
        import azure.cognitiveservices.speech as speechsdk
    except ImportError as exc:
        raise SpeechSmokeError(
            "Speech SDK is missing; install the package with the [speech] extra."
        ) from exc

    key = os.environ.get("AZURE_SPEECH_KEY")
    endpoint = os.environ.get("AZURE_SPEECH_ENDPOINT")
    language = os.environ.get("AZURE_SPEECH_LANGUAGE", "en-US")
    if not key or not endpoint:
        raise SpeechSmokeError(
            "Set AZURE_SPEECH_KEY and AZURE_SPEECH_ENDPOINT in the environment."
        )

    speech_config = speechsdk.SpeechConfig(subscription=key, endpoint=endpoint)
    speech_config.speech_recognition_language = language
    audio_format = speechsdk.audio.AudioStreamFormat(
        samples_per_second=config.sample_rate,
        bits_per_sample=16,
        channels=config.channels,
    )
    push_stream = speechsdk.audio.PushAudioInputStream(stream_format=audio_format)
    audio_config = speechsdk.audio.AudioConfig(stream=push_stream)
    transcriber = speechsdk.transcription.ConversationTranscriber(
        speech_config=speech_config,
        audio_config=audio_config,
    )

    session_stopped = threading.Event()
    canceled = threading.Event()
    cancellation_messages: list[str] = []
    final_segments = [0]

    def on_transcribed(event) -> None:
        result = event.result
        if result.reason == speechsdk.ResultReason.RecognizedSpeech and result.text:
            speaker = result.speaker_id or "Unknown"
            start_seconds = result.offset / 10_000_000
            end_seconds = (result.offset + result.duration) / 10_000_000
            print(
                f"[{start_seconds:7.2f}-{end_seconds:7.2f}s] "
                f"{speaker}: {result.text}",
                flush=True,
            )
            final_segments[0] += 1

    def on_canceled(event) -> None:
        details = speechsdk.CancellationDetails(event.result)
        message = f"reason={details.reason}, error_code={details.error_code}"
        if details.error_details:
            message += f": {details.error_details}"
        cancellation_messages.append(message)
        canceled.set()

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
        print(
            f"Streaming {config.device} at {config.sample_rate} Hz, "
            f"{config.channels} channel(s) for up to {config.duration_seconds}s. "
            "Speak naturally; only finalized results are printed.",
            flush=True,
        )
        process = subprocess.Popen(
            build_raw_capture_command(
                device=config.device,
                sample_rate=config.sample_rate,
                channels=config.channels,
                duration_seconds=config.duration_seconds,
            ),
            stdout=subprocess.PIPE,
            bufsize=0,
        )
        if process.stdout is None:
            raise SpeechSmokeError("Could not read PCM from arecord.")

        deadline = time.monotonic() + config.duration_seconds + 5
        while time.monotonic() < deadline and not canceled.is_set():
            chunk = process.stdout.read(3_200)
            if chunk:
                push_stream.write(chunk)
                continue

            return_code = process.poll()
            if return_code is not None:
                if return_code != 0:
                    raise SpeechSmokeError(f"arecord exited with code {return_code}.")
                break
        else:
            if not canceled.is_set():
                raise SpeechSmokeError("Audio capture exceeded its time limit.")
    except OSError as exc:
        raise SpeechSmokeError(f"Could not start or read from arecord: {exc}") from exc
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

    if canceled.is_set():
        detail = cancellation_messages[-1] if cancellation_messages else "no details"
        raise SpeechSmokeError(f"Azure Speech canceled the session: {detail}")
    if final_segments[0] == 0:
        print("No finalized speech was recognized during the capture.", file=sys.stderr)
    else:
        print(f"Received {final_segments[0]} finalized segment(s).", flush=True)
    return final_segments[0]


def _positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stream microphone audio to Azure Speech and print diarized results."
    )
    parser.add_argument("--device", default="hw:CARD=M0,DEV=0")
    parser.add_argument("--duration-seconds", type=_positive_integer, default=30)
    parser.add_argument("--sample-rate", type=_positive_integer, default=16_000)
    parser.add_argument("--channels", type=_positive_integer, default=1)
    args = parser.parse_args()

    try:
        run_smoke_test(
            SmokeTestConfig(
                device=args.device,
                duration_seconds=args.duration_seconds,
                sample_rate=args.sample_rate,
                channels=args.channels,
            )
        )
    except SpeechSmokeError as exc:
        parser.exit(1, f"Speech smoke test failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
