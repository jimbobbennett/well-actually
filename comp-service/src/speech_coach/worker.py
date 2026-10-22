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


def configure_logging(log_directory=Path("logs")):
    log_directory.mkdir(parents=True, exist_ok=True)
    # Unix epoch nanoseconds distinguish even rapid starts in the same second.
    debug_path = log_directory / f"debug-{time.time_ns()}.log"
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    debug = logging.FileHandler(debug_path, mode="x", encoding="utf-8")
    debug.setLevel(logging.DEBUG)
    errors = logging.FileHandler(log_directory / "worker-errors.log", encoding="utf-8")
    errors.setLevel(logging.ERROR)
    for handler in (console, debug):
        handler.addFilter(lambda record: record.name == __name__ or
                          record.name.startswith("speech_coach."))
    formatter = logging.Formatter("%(asctime)sZ %(levelname)s %(name)s %(message)s")
    formatter.converter = time.gmtime
    logging.basicConfig(level=logging.DEBUG, handlers=[console, debug, errors], force=True)
    for handler in (console, debug, errors):
        handler.setFormatter(formatter)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    LOG.info("Debug log created: %s", debug_path)
    return debug_path


@dataclass
class Session:
    last_evaluated: str | None = None
    last_triggered_turn: str | None = None
    last_attempt: float | None = None


def process(context, classifier, pavlok, session, settings, repository, clock=time.monotonic):
    if context is None:
        LOG.debug("LLM skipped: no eligible speaker-transition context")
        return
    entry = context.current[-1]
    newest = entry.time.isoformat()
    if not settings.testing_mode and session.last_evaluated == newest:
        LOG.debug("LLM skipped: row already evaluated; row_time=%s", newest)
        return
    key = context.turn_key
    if not settings.testing_mode and session.last_triggered_turn == key:
        LOG.debug("LLM skipped: turn already triggered; turn=%s", key)
        return
    # Failed analysis can retry while this speaker transition remains in the window.
    started = time.monotonic()
    LOG.info("LLM call starting: row_time=%s; speaker=%s; previous_rows=%s; current_rows=%s",
             newest, entry.sid, len(context.previous), len(context.current))
    try:
        decision = classifier.evaluate(context)
    except Exception as error:
        LOG.error("LLM call failed: error_type=%s; elapsed_seconds=%.3f",
                  type(error).__name__, time.monotonic() - started)
        raise
    LOG.info("LLM decision: condescending=%s; reexplaining=%s; confidence=%s; "
             "tone=%s; threshold=%s; qualifies=%s; elapsed_seconds=%.3f",
             decision.condescending, decision.reexplaining, decision.confidence,
             json.dumps(decision.tone), settings.confidence,
             decision.triggers(settings.confidence), time.monotonic() - started)
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
                    LOG.info("Pavlok request starting: stimulus_type=%s; strength=%s",
                             settings.stimulus_type, settings.strength)
                    status = pavlok.vibrate()
                except Exception as error:
                    LOG.error("Pavlok outcome uncertain (%s); automatic retry suppressed", type(error).__name__)
                    status = "delivery_unknown"
                LOG.info("Pavlok result: status=%s; row_time=%s; speaker=%s",
                         status, newest, entry.sid)
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
                    try:
                        repository.mark_zap_sent(entry)
                    except Exception as error:
                        LOG.error("zap_sent update failed after Pavlok acceptance: "
                                  "row_time=%s; speaker=%s; error_type=%s",
                                  newest, entry.sid, type(error).__name__)
                        raise
                    LOG.info("zap_sent updated: value=true; row_time=%s; speaker=%s",
                             newest, entry.sid)
        else:
            status = "cooldown"
            LOG.info("Pavlok skipped: cooldown; remaining_seconds=%.3f",
                     settings.cooldown - (now - session.last_attempt))
    LOG.debug("Evaluation complete: status=%s; row_time=%s", status, newest)
    session.last_evaluated = newest


def main():
    parser = argparse.ArgumentParser(description="Poll speech_log for opt-in conversation coaching")
    parser.add_argument("--once", action="store_true", help="Check the rolling window once and exit")
    args = parser.parse_args()
    configure_logging()
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
                    # Provider error bodies can echo transcripts or credentials.
                    LOG.error("LLM request failed: HTTP=%s; error_type=%s; retrying on next poll",
                              error.status_code, type(error).__name__)
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
