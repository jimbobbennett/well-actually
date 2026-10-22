from datetime import datetime
import logging
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from speech_coach.llm import Decision
from speech_coach.turns import Context, Entry
from speech_coach.worker import Session, configure_logging, process


class DebugLoggingTests(unittest.TestCase):
    def setUp(self):
        self.root = logging.getLogger()
        self.saved_handlers = self.root.handlers[:]
        self.saved_level = self.root.level
        # Preserve the test runner's handlers when basicConfig(force=True) runs.
        self.root.handlers = []
        self.logger_levels = {name: logging.getLogger(name).level for name in ("httpx", "openai")}
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.restore_logging)

    def restore_logging(self):
        for handler in self.root.handlers:
            handler.close()
        self.root.handlers = self.saved_handlers
        self.root.setLevel(self.saved_level)
        for name, level in self.logger_levels.items():
            logging.getLogger(name).setLevel(level)
        self.directory.cleanup()

    def test_unique_epoch_files_and_application_only_debug_messages(self):
        directory = Path(self.directory.name)
        first = configure_logging(directory)
        logging.getLogger("speech_coach.database").debug("Context skipped: same speaker")
        logging.getLogger("unrelated.library").warning("private-provider-content")
        second = configure_logging(directory)
        self.assertNotEqual(first, second)
        self.assertRegex(first.name, r"^debug-\d+\.log$")
        self.assertIn("Context skipped: same speaker", first.read_text())
        self.assertNotIn("private-provider-content", first.read_text())
        self.assertTrue(second.exists())

    def test_llm_skip_and_negative_decision_are_logged_without_transcript(self):
        path = configure_logging(Path(self.directory.name))
        settings = SimpleNamespace(testing_mode=False, confidence=0.85)
        process(None, None, None, Session(), settings, None)
        row = Entry(datetime(2026, 10, 22), 2, "private-transcript-content")
        context = Context(previous=(row,), current=(row,))
        classifier = SimpleNamespace(evaluate=lambda _: Decision(False, False, 0.2, "neutral"))
        session = Session()
        # No device object: a negative decision must never attempt a device call.
        process(context, classifier, None, session, settings, None)
        process(context, classifier, None, session, settings, None)
        content = path.read_text()
        for expected in ("LLM skipped: no eligible", "LLM call starting:", "LLM decision:",
                         "qualifies=False", "status=no_trigger", "row already evaluated"):
            self.assertIn(expected, content)
        self.assertNotIn("private-transcript-content", content)


if __name__ == "__main__":
    unittest.main()
