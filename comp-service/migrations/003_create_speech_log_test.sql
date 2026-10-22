BEGIN;

CREATE TABLE public.speech_log_test (
    time TIMESTAMP PRIMARY KEY,
    sid INTEGER,
    content TEXT,
    ms_score INTEGER
);

INSERT INTO public.speech_log_test (time, sid, content, ms_score)
SELECT time, sid, content, ms_score
FROM public.speech_log
WHERE time >= TIMESTAMP '2026-10-22T09:00:00'
  AND time <= TIMESTAMP '2026-10-22T09:09:30'
ORDER BY time;

COMMIT;
