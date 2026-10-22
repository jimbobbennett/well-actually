from datetime import datetime, timedelta
import logging
import psycopg
from psycopg import sql

from .turns import Context, Entry

LOG = logging.getLogger(__name__)


class SpeechLog:
    def __init__(self, settings):
        self.settings = settings

    def connect(self):
        return psycopg.connect(self.settings.database_url, autocommit=True)

    def mark_zap_sent(self, entry):
        table_name = "speech_log_test" if self.settings.testing_mode else "speech_log"
        query = sql.SQL("""UPDATE {table} SET zap_sent = TRUE
            WHERE time = %s AND sid = %s""").format(
                table=sql.Identifier("public", table_name))
        with self.connect() as conn:
            with conn.transaction():
                result = conn.execute(query, (entry.time, entry.sid))
                if result.rowcount != 1:
                    raise RuntimeError("Expected exactly one triggering speech row")

    def recent_context(self):
        table_name = "speech_log_test" if self.settings.testing_mode else "speech_log"
        query = sql.SQL("""WITH window_end AS (
                SELECT CASE WHEN %s THEN (SELECT max(time) FROM {table})
                    ELSE CURRENT_TIMESTAMP AT TIME ZONE 'UTC' END AS timestamp
            )
            SELECT time, sid, content, ms_score FROM {table}, window_end
            WHERE time >= window_end.timestamp - %s
              AND time <= window_end.timestamp
            ORDER BY time DESC LIMIT %s""").format(table=sql.Identifier("public", table_name))
        with self.connect() as conn:
            rows = conn.execute(query,
                (self.settings.testing_mode,
                 timedelta(seconds=self.settings.lookback_seconds),
                 self.settings.context_rows + 1)).fetchall()
        # Only evaluate a transition: the newest two entries must be different speakers.
        LOG.debug("Database rows fetched: table=%s; rows=%s", table_name, len(rows))
        if len(rows) < 2:
            LOG.debug("Context skipped: fewer than two rows in window")
            return None
        if rows[0][1] == rows[1][1]:
            LOG.debug("Context skipped: newest two rows have same speaker; speaker=%s", rows[0][1])
            return None
        current = Entry(*rows[0])
        previous_end = Entry(*rows[1])
        if current.sid is None or previous_end.sid is None or not current.content:
            LOG.debug("Context skipped: missing speaker ID or empty current content")
            return None
        previous_query = sql.SQL("""SELECT
                string_agg(COALESCE(content, ''), E'\\n' ORDER BY time) AS turn_text,
                json_agg(json_build_object(
                    'time', time, 'sid', sid, 'content', content, 'ms_score', ms_score
                ) ORDER BY time) AS source_rows
            FROM {table}
            WHERE sid = %s AND time <= %s
              AND time > COALESCE((
                  SELECT max(time) FROM {table}
                  WHERE time < %s AND sid IS DISTINCT FROM %s
              ), '-infinity'::timestamp)""").format(table=sql.Identifier("public", table_name))
        with self.connect() as conn:
            previous_text, previous_rows = conn.execute(previous_query,
                (previous_end.sid, previous_end.time, previous_end.time, previous_end.sid)).fetchone()
        if not previous_rows or not previous_text or not previous_text.strip():
            LOG.debug("Context skipped: empty previous speaker turn")
            return None
        previous = tuple(Entry(datetime.fromisoformat(row['time']), row['sid'],
                               row['content'], row['ms_score']) for row in previous_rows)
        LOG.debug("Context ready: previous_rows=%s; current_rows=1; row_time=%s; speaker=%s",
                  len(previous), current.time.isoformat(), current.sid)
        return Context(previous=previous, current=(current,), previous_text=previous_text)
