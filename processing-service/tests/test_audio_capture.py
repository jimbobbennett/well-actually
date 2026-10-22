import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from well_actually_processing.audio_capture import CaptureError, record_wav


class AudioCaptureTests(unittest.TestCase):
    def test_record_writes_valid_wav_from_arecord_output(self):
        def fake_arecord(arguments, **_kwargs):
            output_path = Path(arguments[-1])
            with wave.open(str(output_path), "wb") as recording:
                recording.setnchannels(1)
                recording.setsampwidth(2)
                recording.setframerate(16_000)
                recording.writeframes(b"\x00\x00" * 16_000)
            return subprocess.CompletedProcess(arguments, 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture.wav"
            with patch("well_actually_processing.audio_capture.subprocess.run", fake_arecord):
                info = record_wav(output, duration_seconds=1)

            self.assertTrue(output.is_file())
            self.assertEqual(info.frames, 16_000)
            self.assertEqual(info.sample_rate, 16_000)
            self.assertEqual(info.sample_width_bytes, 2)

    def test_arecord_failure_does_not_leave_partial_capture(self):
        def failed_arecord(arguments, **_kwargs):
            return subprocess.CompletedProcess(arguments, 1, stdout="", stderr="No such device")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture.wav"
            with patch("well_actually_processing.audio_capture.subprocess.run", failed_arecord):
                with self.assertRaisesRegex(CaptureError, "No such device"):
                    record_wav(output)

            self.assertFalse(output.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
