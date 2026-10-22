import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app import app, encode_sse, parse_cursor, serialize_record


class DashboardTests(unittest.TestCase):
    def test_homepage_serves_dashboard(self):
        response = TestClient(app).get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Conversation", response.text)
        self.assertIn('id="theme-toggle"', response.text)
        self.assertIn('aria-label="Dark mode"', response.text)
        self.assertNotIn("CONVERSATION STUDIO", response.text)
        self.assertNotIn("REAL-TIME SPEECH INSIGHTS", response.text)
        self.assertNotIn("Every voice", response.text)
        self.assertNotIn("Built for the back-and-forth.", response.text)
        self.assertNotIn("Transcript text is served", response.text)
        self.assertNotIn("Distinct colors make every speaker easy to follow.", response.text)
        self.assertNotIn("THE ROOM", response.text)
        self.assertNotIn("speaker-list", response.text)
        self.assertNotIn("<aside", response.text)
        self.assertNotIn("Segments received", response.text)
        self.assertNotIn("Voices in the room", response.text)
        self.assertNotIn("Most recent speech", response.text)
        self.assertNotIn("<footer", response.text)

    def test_speech_row_serializes_utc_timestamp_and_nullable_fields(self):
        row = {
            "time": datetime(2026, 10, 22, 18, 30, 15, 123456),
            "sid": 2,
            "content": "Hello!",
            "ms_score": None,
            "zap_sent": True,
        }

        record = serialize_record(row)

        self.assertEqual(record["time"], "2026-10-22T18:30:15.123456")
        self.assertEqual(record["sid"], 2)
        self.assertEqual(record["content"], "Hello!")
        self.assertIsNone(record["ms_score"])
        self.assertTrue(record["zap_sent"])
        row["zap_sent"] = False
        self.assertFalse(serialize_record(row)["zap_sent"])

    def test_cursor_accepts_utc_event_id(self):
        cursor = parse_cursor("2026-10-22T18:30:15.123456Z")

        self.assertEqual(cursor, datetime(2026, 10, 22, 18, 30, 15, 123456))
        self.assertIsNone(cursor.tzinfo)

    def test_cursor_normalizes_timezone_aware_values_to_utc(self):
        cursor = parse_cursor("2026-10-22T11:30:15-07:00")

        self.assertEqual(cursor, datetime(2026, 10, 22, 18, 30, 15))

    def test_invalid_cursor_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_cursor("not-a-timestamp")

    def test_sse_json_escapes_transcript_newlines(self):
        message = encode_sse(
            "speech",
            {"content": "first line\nsecond line"},
            "2026-10-22T18:30:15.123456",
        )

        self.assertIn("id: 2026-10-22T18:30:15.123456\n", message)
        self.assertIn('data: {"content":"first line\\nsecond line"}\n\n', message)


if __name__ == "__main__":
    unittest.main()
