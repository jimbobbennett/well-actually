#!/usr/bin/env python3
"""Generate synthetic, fixed-window wake-word audio with Azure Speech."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import random
import struct
import subprocess
import time
import urllib.error
import urllib.request
import wave
from datetime import datetime, timezone
from pathlib import Path


SAMPLE_RATE = 16_000
WINDOW_MS = 2_000
WINDOW_FRAMES = SAMPLE_RATE * WINDOW_MS // 1_000
PITCHES = (-12, -4, 4, 12)
RATES = (90, 110)
VOICES = (
    "en-US-JennyNeural",
    "en-US-GuyNeural",
    "en-US-AriaNeural",
    "en-US-DavisNeural",
    "en-GB-SoniaNeural",
    "en-GB-RyanNeural",
    "en-AU-NatashaNeural",
    "en-AU-WilliamNeural",
    "en-IN-NeerjaNeural",
    "en-IN-PrabhatNeural",
)
NEGATIVE_PHRASES = (
    "Well, I think so.",
    "Actually, I agree.",
    "We'll have to wait.",
    "What do you think?",
    "I hear you.",
    "Let's try again.",
    "Where are we?",
    "We can do that.",
)
TRAINING_VOICE_COUNT = 8
NOISE_SAMPLES = {"training": 12, "testing": 4}


def get_speech_key(resource_group: str, resource_name: str) -> str:
    try:
        result = subprocess.run(
            [
                "az",
                "cognitiveservices",
                "account",
                "keys",
                "list",
                "--resource-group",
                resource_group,
                "--name",
                resource_name,
                "--query",
                "key1",
                "--output",
                "tsv",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            "Could not retrieve the Speech key with Azure CLI. Check az login "
            "and access to the configured Speech resource."
        ) from exc

    key = result.stdout.strip()
    if not key:
        raise RuntimeError("Azure CLI returned an empty Speech key.")
    return key


def speech_request(
    text: str,
    voice: str,
    pitch: int,
    rate: int,
    region: str,
    speech_key: str,
) -> bytes:
    language = "-".join(voice.split("-")[:2])
    pitch_text = f"{pitch:+d}%"
    safe_text = html.escape(text)
    ssml = (
        "<?xml version='1.0' encoding='utf-8'?>"
        f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' "
        f"xml:lang='{language}'><voice name='{voice}'>"
        f"<prosody rate='{rate}%' pitch='{pitch_text}'>{safe_text}</prosody>"
        "</voice></speak>"
    ).encode("utf-8")
    request = urllib.request.Request(
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
        data=ssml,
        headers={
            "Ocp-Apim-Subscription-Key": speech_key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "riff-16khz-16bit-mono-pcm",
            "User-Agent": "well-actually-wake-word-dataset",
        },
    )

    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise RuntimeError(
                    f"Azure Speech synthesis failed with HTTP {exc.code} "
                    f"for voice {voice}."
                ) from exc
            time.sleep(2**attempt)
        except urllib.error.URLError as exc:
            if attempt == 3:
                raise RuntimeError(
                    f"Could not connect to Azure Speech for voice {voice}."
                ) from exc
            time.sleep(2**attempt)

    raise RuntimeError("Azure Speech synthesis retries were exhausted.")


def fixed_window(wav_bytes: bytes, description: str) -> bytes:
    import io

    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as source:
            if (
                source.getframerate() != SAMPLE_RATE
                or source.getnchannels() != 1
                or source.getsampwidth() != 2
            ):
                raise RuntimeError(
                    f"Unexpected WAV format returned for {description}; "
                    "expected 16 kHz, mono, 16-bit PCM."
                )
            frames = source.readframes(source.getnframes())
    except wave.Error as exc:
        raise RuntimeError(f"Azure returned an invalid WAV for {description}.") from exc

    samples = list(struct.unpack(f"<{len(frames) // 2}h", frames))
    if len(samples) > WINDOW_FRAMES:
        trailing = samples[WINDOW_FRAMES:]
        tail_rms = math.sqrt(sum(sample * sample for sample in trailing) / len(trailing))
        if tail_rms > 100:
            duration = len(samples) / SAMPLE_RATE
            raise RuntimeError(
                f"Speech for {description} is {duration:.2f}s and does not fit "
                f"the {WINDOW_MS}ms model window. Increase WINDOW_MS before retrying."
            )
        samples = samples[:WINDOW_FRAMES]
    else:
        samples.extend([0] * (WINDOW_FRAMES - len(samples)))

    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(SAMPLE_RATE)
        target.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return output.getvalue()


def add_background_noise(wav_bytes: bytes, seed_text: str) -> bytes:
    import io

    rng = random.Random(int.from_bytes(hashlib.sha256(seed_text.encode()).digest()[:8], "big"))
    with wave.open(io.BytesIO(wav_bytes), "rb") as source:
        samples = list(struct.unpack(f"<{WINDOW_FRAMES}h", source.readframes(WINDOW_FRAMES)))

    signal_rms = math.sqrt(sum(sample * sample for sample in samples) / WINDOW_FRAMES)
    noise_rms = max(signal_rms / (10 ** (25 / 20)), 90)
    noise = [rng.gauss(0, noise_rms) for _ in samples]
    mixed = [
        max(-32768, min(32767, round(sample + extra)))
        for sample, extra in zip(samples, noise)
    ]

    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(SAMPLE_RATE)
        target.writeframes(struct.pack(f"<{len(mixed)}h", *mixed))
    return output.getvalue()


def make_noise_only(seed: int) -> bytes:
    rng = random.Random(seed)
    previous = 0.0
    samples = []
    for _ in range(WINDOW_FRAMES):
        previous = 0.94 * previous + 0.06 * rng.gauss(0, 1_000)
        samples.append(max(-32768, min(32767, round(previous))))

    import io

    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(SAMPLE_RATE)
        target.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return output.getvalue()


def write_variants(
    output_dir: Path,
    split: str,
    label: str,
    name: str,
    clean_wav: bytes,
) -> list[dict[str, str]]:
    class_dir = output_dir / split / label
    class_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for variant, wav_bytes in (
        ("clean", clean_wav),
        ("room-noise", add_background_noise(clean_wav, f"{split}/{name}")),
    ):
        filename = f"{name}__{variant}.wav"
        path = class_dir / filename
        path.write_bytes(wav_bytes)
        records.append(
            {
                "split": split,
                "label": label,
                "file": path.relative_to(output_dir).as_posix(),
                "synthetic": "true",
                "augmentation": variant,
            }
        )
    return records


def generate(output_dir: Path, resource_group: str, resource_name: str, region: str) -> None:
    if any(output_dir.rglob("*.wav")) or (output_dir / "manifest.json").exists():
        raise RuntimeError(
            f"{output_dir} already contains generated data. Choose a new output "
            "directory rather than overwriting it."
        )

    speech_key = get_speech_key(resource_group, resource_name)
    voice_list_url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/voices/list"
    voice_request = urllib.request.Request(
        voice_list_url, headers={"Ocp-Apim-Subscription-Key": speech_key}
    )
    try:
        with urllib.request.urlopen(voice_request, timeout=30) as response:
            available_voices = {item["ShortName"] for item in json.load(response)}
    except (urllib.error.URLError, json.JSONDecodeError, KeyError) as exc:
        raise RuntimeError("Could not verify available Azure Speech voices.") from exc

    missing_voices = sorted(set(VOICES) - available_voices)
    if missing_voices:
        raise RuntimeError(
            "These configured synthetic voices are unavailable in this Speech "
            f"resource: {', '.join(missing_voices)}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, str]] = []
    voice_splits = {
        voice: "training" if index < TRAINING_VOICE_COUNT else "testing"
        for index, voice in enumerate(VOICES)
    }

    for voice_index, voice in enumerate(VOICES):
        split = voice_splits[voice]
        voice_slug = voice.lower().replace("neural", "").replace("-", "_")
        for pitch in PITCHES:
            for rate in RATES:
                pitch_slug = f"{'plus' if pitch > 0 else 'minus'}{abs(pitch)}"
                name = (
                    f"target__{voice_slug}__pitch-{pitch_slug}__rate-{rate:03d}"
                )
                wav_bytes = speech_request(
                    "Well actually",
                    voice,
                    pitch,
                    rate,
                    region,
                    speech_key,
                )
                clip = fixed_window(
                    wav_bytes, f"{voice}, pitch {pitch:+d}%, rate {rate}%"
                )
                records.extend(
                    write_variants(output_dir, split, "well-actually", name, clip)
                )

        for phrase_index, phrase in enumerate(NEGATIVE_PHRASES):
            pitch = PITCHES[(voice_index + phrase_index) % len(PITCHES)]
            rate = RATES[(voice_index + phrase_index) % len(RATES)]
            name = f"other-speech__{voice_slug}__phrase-{phrase_index + 1:02d}"
            wav_bytes = speech_request(phrase, voice, pitch, rate, region, speech_key)
            clip = fixed_window(wav_bytes, f"{voice}, negative phrase {phrase_index + 1}")
            records.extend(write_variants(output_dir, split, "noise", name, clip))

    for split, count in NOISE_SAMPLES.items():
        for index in range(count):
            name = f"ambient-noise__{split}-{index + 1:02d}"
            records.extend(
                write_variants(
                    output_dir,
                    split,
                    "noise",
                    name,
                    make_noise_only(index + (0 if split == "training" else 10_000)),
                )
            )

    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": "Azure AI Speech text-to-speech; no human recordings",
        "speech_resource": resource_name,
        "speech_region": region,
        "sample_rate_hz": SAMPLE_RATE,
        "channels": 1,
        "sample_format": "16-bit PCM WAV",
        "window_ms": WINDOW_MS,
        "target_phrase": "Well actually",
        "voices": list(VOICES),
        "pitch_percent": list(PITCHES),
        "rate_percent": list(RATES),
        "training_voices": list(VOICES[:TRAINING_VOICE_COUNT]),
        "held_out_test_voices": list(VOICES[TRAINING_VOICE_COUNT:]),
        "negative_phrases": list(NEGATIVE_PHRASES),
        "samples": records,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    counts: dict[str, dict[str, int]] = {}
    for record in records:
        split = record["split"]
        label = record["label"]
        counts.setdefault(split, {}).setdefault(label, 0)
        counts[split][label] += 1
    print(f"Generated dataset at {output_dir}")
    for split, labels in counts.items():
        print(f"  {split}: " + ", ".join(f"{label}={count}" for label, count in labels.items()))
    print(f"  sample format: mono {SAMPLE_RATE} Hz, {WINDOW_MS} ms, 16-bit PCM WAV")


def main() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=repository_root / "data" / "wake-word",
        help="output directory (default: data/wake-word)",
    )
    parser.add_argument("--resource-group", default="rg_well_actually")
    parser.add_argument("--speech-resource", default="wellactually-speech-jb-1022")
    parser.add_argument("--region", default="westus2")
    args = parser.parse_args()
    try:
        generate(args.output.resolve(), args.resource_group, args.speech_resource, args.region)
    except (OSError, RuntimeError, urllib.error.URLError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
