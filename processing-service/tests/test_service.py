import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from well_actually_processing.service import (
    build_speech_log_record,
    speaker_id_to_number,
)


class SpeechLogMappingTests(unittest.TestCase):
    def test_guest_speaker_id_maps_to_integer(self):
        self.assertEqual(speaker_id_to_number("Guest-1"), 1)
        self.assertEqual(speaker_id_to_number("Guest-12"), 12)

    def test_unknown_speaker_id_maps_to_null(self):
        self.assertIsNone(speaker_id_to_number(None))
        self.assertIsNone(speaker_id_to_number("Unknown"))

    def test_record_time_is_utc_naive_with_segment_offset(self):
        origin = datetime(
            2026, 10, 22, 12, 0, tzinfo=timezone(timedelta(hours=-7))
        )
        result = SimpleNamespace(
            text="  hello there  ",
            offset=15_000_000,
            speaker_id="Guest-2",
        )

        record = build_speech_log_record(result, origin)

        self.assertEqual(record.time, datetime(2026, 10, 22, 19, 0, 1, 500_000))
        self.assertIsNone(record.time.tzinfo)
        self.assertEqual(record.sid, 2)
        self.assertEqual(record.content, "  hello there  ")

    def test_empty_text_is_not_persisted(self):
        result = SimpleNamespace(text="  ", offset=0, speaker_id="Guest-1")

        self.assertIsNone(
            build_speech_log_record(result, datetime.now(timezone.utc))
        )


if __name__ == "__main__":
    unittest.main()
