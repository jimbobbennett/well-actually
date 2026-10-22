import sys
import unittest
from datetime import datetime, timedelta, timezone
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from well_actually_processing.pavlok import PavlokClientError
from well_actually_processing.service import (
    _on_well_actually_detected,
    build_speech_log_record,
    speaker_id_to_number,
    SpeechLogStore,
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
        self.assertFalse(record.zap_sent)

    def test_record_marks_successful_vibe_request(self):
        result = SimpleNamespace(text="Well actually", offset=0, speaker_id=None)
        origin = datetime.now(timezone.utc)

        record = build_speech_log_record(result, origin, zap_sent=True)

        self.assertTrue(record.zap_sent)

    def test_empty_text_is_not_persisted(self):
        result = SimpleNamespace(text="  ", offset=0, speaker_id="Guest-1")

        self.assertIsNone(
            build_speech_log_record(result, datetime.now(timezone.utc))
        )


class PhraseDetectionActionTests(unittest.TestCase):
    def test_phrase_detection_signals_led_and_sends_vibe(self):
        led_indicator = Mock()
        pavlok_client = Mock()

        zap_sent = _on_well_actually_detected(led_indicator, pavlok_client)

        led_indicator.show_phrase_detected.assert_called_once_with()
        pavlok_client.send_vibe.assert_called_once_with()
        self.assertTrue(zap_sent)

    def test_pavlok_failure_does_not_prevent_led_signal(self):
        led_indicator = Mock()
        pavlok_client = Mock()
        pavlok_client.send_vibe.side_effect = PavlokClientError("request failed")

        with self.assertLogs("well_actually_processing", level="ERROR"):
            zap_sent = _on_well_actually_detected(led_indicator, pavlok_client)

        led_indicator.show_phrase_detected.assert_called_once_with()
        self.assertFalse(zap_sent)

    def test_missing_pavlok_configuration_does_not_mark_zap_sent(self):
        self.assertFalse(_on_well_actually_detected(Mock()))


class SpeechLogStoreTests(unittest.TestCase):
    def test_insert_persists_zap_sent_flag(self):
        connection = Mock()
        connection.closed = False
        psycopg = ModuleType("psycopg")
        psycopg.Error = Exception
        psycopg.connect = Mock(return_value=connection)
        record = SimpleNamespace(
            time=datetime(2026, 10, 22, 20, 0),
            sid=1,
            content="Well actually",
            zap_sent=True,
        )

        with patch.dict(sys.modules, {"psycopg": psycopg}):
            store = SpeechLogStore("postgresql://test")
            store.insert(record)

        self.assertIn('"zap_sent"', connection.execute.call_args_list[0].args[0])
        self.assertEqual(
            connection.execute.call_args_list[-1].args[1],
            (record.time, record.sid, record.content, None, True),
        )
        connection.commit.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
