"""List ALSA audio inputs and capture bounded WAV recordings with arecord."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path


class CaptureError(RuntimeError):
    """Raised when an audio device cannot be listed or recorded."""


@dataclass(frozen=True)
class RecordingInfo:
    path: Path
    channels: int
    sample_rate: int
    sample_width_bytes: int
    frames: int


def build_raw_capture_command(
    *,
    device: str,
    sample_rate: int,
    channels: int,
    duration_seconds: int | None = None,
) -> list[str]:
    if sample_rate <= 0 or channels <= 0:
        raise ValueError("Sample rate and channel count must be positive.")
    if duration_seconds is not None and duration_seconds <= 0:
        raise ValueError("Duration must be positive when provided.")

    command = [
        "arecord",
        "-q",
        "-D",
        device,
        "-t",
        "raw",
        "-f",
        "S16_LE",
        "-r",
        str(sample_rate),
        "-c",
        str(channels),
    ]
    if duration_seconds is not None:
        command.extend(["-d", str(duration_seconds)])
    command.append("-")
    return command


def _run_arecord(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["arecord", *arguments],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise CaptureError(
            "arecord is unavailable; install ALSA utilities (for example, "
            "'sudo apt install alsa-utils')."
        ) from exc

    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit code {result.returncode}"
        raise CaptureError(f"arecord failed: {detail}")
    return result


def list_devices() -> str:
    sections = []
    for title, arguments in (
        ("Hardware capture devices", ["-l"]),
        ("Available capture PCM names", ["-L"]),
    ):
        result = _run_arecord(arguments)
        sections.append(f"{title}:\n{result.stdout.strip() or '(none reported)'}")
    return "\n\n".join(sections)


def record_wav(
    output: Path,
    *,
    duration_seconds: int = 5,
    device: str = "default",
    sample_rate: int = 16_000,
    channels: int = 1,
) -> RecordingInfo:
    if duration_seconds <= 0 or sample_rate <= 0 or channels <= 0:
        raise ValueError("Duration, sample rate, and channel count must be positive.")

    output = output.expanduser()
    if output.exists():
        raise CaptureError(f"Refusing to overwrite existing recording: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        prefix=f".{output.stem}.",
        suffix=".wav",
        dir=output.parent,
        delete=False,
    ) as temporary_file:
        temporary_path = Path(temporary_file.name)

    try:
        _run_arecord(
            [
                "-q",
                "-D",
                device,
                "-t",
                "wav",
                "-f",
                "S16_LE",
                "-r",
                str(sample_rate),
                "-c",
                str(channels),
                "-d",
                str(duration_seconds),
                str(temporary_path),
            ]
        )

        try:
            with wave.open(str(temporary_path), "rb") as recording:
                info = RecordingInfo(
                    path=output,
                    channels=recording.getnchannels(),
                    sample_rate=recording.getframerate(),
                    sample_width_bytes=recording.getsampwidth(),
                    frames=recording.getnframes(),
                )
        except (OSError, wave.Error) as exc:
            raise CaptureError(f"arecord did not produce a valid WAV file: {exc}") from exc

        if info.frames <= 0:
            raise CaptureError("The capture completed but contained no audio frames.")
        if info.channels != channels or info.sample_rate != sample_rate:
            raise CaptureError(
                "The recording format differs from the requested format "
                f"({info.channels} channels at {info.sample_rate} Hz)."
            )

        temporary_path.replace(output)
        return info
    finally:
        temporary_path.unlink(missing_ok=True)


def _positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture audio from an ALSA input to WAV.")
    parser.add_argument("--list-devices", action="store_true", help="list ALSA capture devices")
    parser.add_argument("--output", type=Path, help="destination WAV file")
    parser.add_argument("--device", default="default", help="ALSA capture device (default: default)")
    parser.add_argument(
        "--duration-seconds",
        type=_positive_integer,
        default=5,
        help="bounded capture length (default: 5)",
    )
    parser.add_argument(
        "--sample-rate",
        type=_positive_integer,
        default=16_000,
        help="requested sample rate in Hz (default: 16000)",
    )
    parser.add_argument(
        "--channels",
        type=_positive_integer,
        default=1,
        help="requested channel count (default: 1)",
    )
    args = parser.parse_args()

    try:
        if args.list_devices:
            print(list_devices())
            return 0
        if args.output is None:
            parser.error("--output is required unless --list-devices is used")

        info = record_wav(
            args.output,
            duration_seconds=args.duration_seconds,
            device=args.device,
            sample_rate=args.sample_rate,
            channels=args.channels,
        )
    except CaptureError as exc:
        parser.exit(1, f"Audio capture error: {exc}\n")

    seconds = info.frames / info.sample_rate
    print(
        f"Saved {info.path}: {seconds:.2f}s, {info.channels} channel(s), "
        f"{info.sample_rate} Hz, {info.sample_width_bytes * 8}-bit PCM."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
