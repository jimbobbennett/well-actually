import unittest

from well_actually_processing.audio_capture import build_raw_capture_command


class SpeechSmokeTests(unittest.TestCase):
    def test_arecord_stream_is_raw_pcm_to_stdout(self):
        command = build_raw_capture_command(
            device="hw:CARD=M0,DEV=0",
            sample_rate=16_000,
            channels=1,
            duration_seconds=7,
        )

        self.assertEqual(command[0], "arecord")
        self.assertEqual(command[command.index("-t") + 1], "raw")
        self.assertEqual(command[command.index("-f") + 1], "S16_LE")
        self.assertEqual(command[command.index("-r") + 1], "16000")
        self.assertEqual(command[command.index("-c") + 1], "1")
        self.assertEqual(command[command.index("-d") + 1], "7")
        self.assertEqual(command[-1], "-")

    def test_continuous_arecord_command_has_no_duration_limit(self):
        command = build_raw_capture_command(
            device="hw:CARD=M0,DEV=0",
            sample_rate=16_000,
            channels=1,
        )

        self.assertNotIn("-d", command)
        self.assertEqual(command[-1], "-")


if __name__ == "__main__":
    unittest.main()
