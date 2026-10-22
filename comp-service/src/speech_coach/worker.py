import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import signal
import threading
import time

from dotenv import load_dotenv

from .config import Settings
from .database import SpeechLog
from .pavlok import Pavlok
from .tracing import setup_tracing

LOG = logging.getLogger(__name__)


@dataclass
class Session:
    last_evaluated: str | None = None
    last_triggered_turn: str | None = None
    last_attempt: float | None = None


def process(context, classifier, pavlok, session, settings, repository, clock=time.monotonic):
    if context is None:
        return
    entry = context.current[-1]
    newest = entry.time.isoformat()
    if not settings.testing_mode and session.last_evaluated == newest:
        return
    key = context.turn_key
    if not settings.testing_mode and session.last_triggered_turn == key:
        return
    # Failed analysis can retry while this speaker transition remains in the window.
    decision = classifier.evaluate(context)
    status = "no_trigger"
    if decision.triggers(settings.confidence):
        now = clock()
        if not settings.testing_mode and session.last_triggered_turn == key:
            status = "turn_already_triggered"
        elif settings.testing_mode or session.last_attempt is None or now - session.last_attempt >= settings.cooldown:
            path = Path(settings.activation_log_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            # Open before the request: do not activate if the log cannot be opened.
            with path.open("a", encoding="utf-8") as logfile:
                session.last_triggered_turn = key
                session.last_attempt = now
                activation_time = datetime.now(timezone.utc).isoformat()
                try:
                    status = pavlok.vibrate()
                except Exception as error:
                    LOG.error("Pavlok outcome uncertain (%s); automatic retry suppressed", type(error).__name__)
                    status = "delivery_unknown"
                record = {
                    "time": activation_time,
                    "status": status,
                    "prompt_version_id": classifier.prompt.version_id,
                    "prompt_label": classifier.prompt.label,
                    "triggering_row": asdict(context.current[-1]),
                    "current_turn_rows": [asdict(row) for row in context.current],
                    "compared_against_rows": [asdict(row) for row in context.previous],
                    "decision": asdict(decision),
                }
                log_entry = json.dumps(record, default=lambda value: value.isoformat())
                logfile.write(log_entry + "\n")
                logfile.flush()
                if status == "accepted":
                    repository.mark_zap_sent(entry)
        else:
            status = "cooldown"
    session.last_evaluated = newest


def main():
    parser = argparse.ArgumentParser(description="Poll speech_log for opt-in conversation coaching")
    parser.add_argument("--once", action="store_true", help="Check the rolling window once and exit")
    args = parser.parse_args()
    console = logging.StreamHandler()
    console.addFilter(lambda record: record.name == __name__ and
                      record.getMessage().startswith(("Process started:", "Starting worker;", "Polling database:", "Loaded Arize prompt:")))
    error_path = Path("logs/worker-errors.log")
    error_path.parent.mkdir(parents=True, exist_ok=True)
    errors = logging.FileHandler(error_path, encoding="utf-8")
    errors.setLevel(logging.ERROR)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[console, errors], force=True)
    # Prevent SDK/HTTP request logs from disclosing configured URLs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    load_dotenv(override=False)
    tracer_provider = None
    try:
        settings = Settings.from_env()
        tracer_provider = setup_tracing(testing_mode=settings.testing_mode)
        run(settings, args.once)
    except Exception as error:
        LOG.error("Worker stopped (%s). Check configuration/connectivity; secret values suppressed.", type(error).__name__)
        raise SystemExit(1) from None
    finally:
        if tracer_provider is not None:
            tracer_provider.shutdown()


def run(settings, once):
    # Import the SDK and create clients only after tracing is initialized.
    from openai import APIStatusError
    from .llm import Classifier

    path = Path(settings.activation_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    startup_record = {
        "event": "process_started",
        "time": datetime.now(timezone.utc).isoformat(),
        "debug_mode": settings.testing_mode,
        "testing_mode": settings.testing_mode,
    }
    with path.open("a", encoding="utf-8") as logfile:
        logfile.write(json.dumps(startup_record) + "\n")
    LOG.info("Process started: %s", json.dumps(startup_record))
    repository = SpeechLog(settings)
    session = Session()
    classifier = Classifier(settings)
    LOG.info("Loaded Arize prompt: label=%s; version=%s",
             classifier.prompt.label, classifier.prompt.version_id)
    pavlok = Pavlok(settings)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    try:
        LOG.info("Starting worker; activation log=%s", settings.activation_log_path)
        while not stop.is_set():
            try:
                LOG.info("Polling database: table=public.%s; lookback=%ss",
                         "speech_log_test" if settings.testing_mode else "speech_log",
                         settings.lookback_seconds)
                context = repository.recent_context()
                process(context, classifier, pavlok, session, settings, repository)
            except Exception as error:
                if isinstance(error, APIStatusError):
                    details = error.body
                    if isinstance(details, dict):
                        details = details.get("error", details)
                    message = details.get("message", error.message) if isinstance(details, dict) else error.message
                    message = str(message)
                    for secret in (settings.api_key, settings.authorization, settings.database_url):
                        if secret:
                            message = message.replace(secret, "[REDACTED]")
                    LOG.error("LLM request failed (HTTP %s): %s; retrying on next poll",
                              error.status_code, json.dumps(message, ensure_ascii=False))
                else:
                    LOG.error("Poll failed (%s); retrying on next poll", type(error).__name__)
                if once:
                    raise
                stop.wait(min(max(settings.poll, 5), 60))
                continue
            if once:
                break
            stop.wait(settings.poll)
    finally:
        pavlok.close()
        classifier.close()


if __name__ == "__main__":
    main()
