# Speech Coach

A hackathon worker that polls recent speech in TigerDB/TimescaleDB, compares a
speaker transition using an external LLM, and activates an opted-in wearer's
Pavlok vibration when it detects condescension or unnecessary re-explanation.

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
cp -n .env.example .env
```

Fill in `DATABASE_URL`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, and
`PAVLOK_AUTHORIZATION` in `.env`. Set `WEARER_OPTED_IN=true` only for a consenting
wearer. Selected dialogue is sent to your configured LLM provider. Qualifying
decisions call Pavlok directly; there is no dry-run flag.

```dotenv
LOOKBACK_SECONDS=120
POLL_SECONDS=5
TESTING_MODE=false
```

```bash
.venv/bin/speech-coach --once
.venv/bin/speech-coach
```

## Arize tracing

### Managed prompts

The classifier loads the prompt selected by `ARIZE_PROMPT_MODE` from Arize Prompt Hub
once at startup using `ARIZE_API_KEY` and the corresponding prompt ID (see `.env.example`).
`TESTING_MODE=true` selects the `staging` label; normal mode selects `production`.
Set `ARIZE_PROMPT_LABEL` to override that selection. Restart the worker after
moving a label to load its new version. Prompt loading or validation failures
stop startup before any device activation; there is no local prompt fallback.

Keep both prompt IDs configured and switch only `ARIZE_PROMPT_MODE`, then restart
the worker:

```dotenv
ARIZE_PROMPT_ID_ORIGINAL=your-original-prompt-id
ARIZE_PROMPT_ID_SENSITIVE=your-sensitive-prompt-id
ARIZE_PROMPT_MODE=sensitive
```

`ARIZE_PROMPT_MODE` accepts `original` or `sensitive` and defaults to `sensitive`.
Invalid modes or a missing selected prompt ID stop startup. The old
`ARIZE_PROMPT_ID` variable is no longer used.

The env example selects the sensitive prompt. It favors detecting borderline
condescension and can produce more false positives and device activations.
Sensitive mode infers tone from textual cues and uses that assessment when
classifying patronizing, mansplaining-like, dismissive, invalidating, and
repetitive explanations. Responses include `tone` and `tone_evidence`, which
are validated and included in activation logs. Tone is inferred from text,
not measured from audio. The original prompt's three-field responses remain
supported; their tone is recorded as null with an empty evidence list.
Both prompts use the same `TRIGGER_CONFIDENCE=0.85`; switching modes does
not change the threshold. The threshold applies to either decision flag; the prompt does not inflate
confidence to force a trigger. Exported shell variables take precedence over
`.env`, so unset or update exported values when switching.

Hub versions must use `F_STRING`, with one SYSTEM message followed by one USER
message, and only the `{conversation_json}` variable. Escape literal JSON braces
as `{{` and `}}`. The app keeps using `OPENAI_BASE_URL`, `OPENAI_MODEL`, and
`OPENAI_API_KEY` for inference; Hub model metadata does not override them.
The loaded version is logged at startup and included in device activation logs.
Prompt Hub access is required even when optional trace export is disabled.

### Trace export

Completed, valid classifier LLM spans include typed `output.condescending` and
`output.reexplaining` booleans and numeric `output.confidence` alongside the
original response and token usage. AX exposes these as `attributes.output.*`.
Invalid, incomplete, and failed responses do not receive these decision fields.
Only spans exported after this change are enriched; historical spans are unchanged.
For a dashboard use `(condescending = true OR reexplaining = true) AND confidence > 0.85`.
The device's existing threshold comparison remains `>=`, so a confidence of exactly
0.85 qualifies for the device but not for that dashboard filter.

Install the project dependencies with `.venv/bin/python -m pip install -e .`.
Set `ARIZE_SPACE_ID`, `ARIZE_API_KEY`, and `ARIZE_PROJECT_NAME` in the ignored
`.env` file to enable OpenAI SDK tracing. The configured project is `speech-coach`.
Tracing sends conversation text, model responses, and call metadata to Arize AX.
Keep the API key private. Tracing starts before the OpenAI client is created,
and the worker flushes pending traces on exit.

Run `.venv/bin/speech-coach --once` for one poll or `.venv/bin/speech-coach`
for continuous polling. Both commands can activate the real Pavlok device,
including in testing mode. A poll must make an LLM call to produce a trace.
Unset exported `ARIZE_*` variables if you want `.env` to control these settings.
Remove the Arize settings to disable tracing.

## Rolling window

Normally each poll reads rows between **database UTC now minus LOOKBACK_SECONDS
and database UTC now**, newest first, independent of the database session timezone.

Set `TESTING_MODE=true` to read **public.speech_log_test** instead of the live
`public.speech_log` table, and use **the newest test-table timestamp minus
LOOKBACK_SECONDS through the newest test-table timestamp**. The test table is
seeded with the original 20 Maya/Daniel dialogue rows by
`migrations/003_create_speech_log_test.sql`. This works with older
data without changing timestamps or needing ongoing writes. For example, if the
newest row is at 09:10:00 and the lookback is 120 seconds, the window is
09:08:00–09:10:00 regardless of the current clock. Testing mode still calls the
real LLM and Pavlok and retains the speaker-transition rule. In testing mode the
LLM is called on every eligible poll, even when the data has not changed. Each
qualifying decision activates Pavlok again: testing mode bypasses both the
once-per-turn guard and cooldown. Normal mode retains those limits.
It is not a dry-run mode.

The existing `time` column is TIMESTAMP WITHOUT TIME ZONE. Live timestamp values
must represent UTC; ingestion must write UTC values. Polling always compares
them with UTC database time, with no configurable timezone. Existing timestamps
are not rewritten. Testing mode remains anchored to the newest test timestamp,
so historical fixtures do not need conversion for testing.

The newest two entries must have different SIDs. The worker compares the newest
speaker's content against the aggregate of immediately preceding consecutive
rows belonging to the previous speaker, in chronological order. PostgreSQL uses
`string_agg` to combine their contents into one previous-turn text value. This
previous turn extends beyond the lookback cutoff when necessary and stops at
the next earlier speaker change. It never merges disconnected turns from the
same SID. The newest speaker transition must still be inside the rolling window.

For example, if the current window contains:

| Relative time | SID | Content |
|---|---|---|
| 0 | 3 | words |
| +30 | 1 | more words |
| +60 | 1 | sentence |
| +90 | 1 | final words |
| +120 | 2 | mansplain |

The LLM compares SID 2's `mansplain` with SID 1's
`more words\nsentence\nfinal words`. SID 3 and any earlier SID 1 turn are excluded.
If the newest two entries have the same SID, that poll skips evaluation. Polling
can miss a transition if another chunk from the same new speaker arrives before
the next poll; decrease POLL_SECONDS if needed for the demo.

Unchanged newest entries are evaluated once per running process, even if the
LLM decides not to trigger. Cooldown and duplicate suppression are in memory and
reset on restart. Model errors can retry on a subsequent poll while the transition
remains in the window. No flags, scores, or processing cursors are written to
TigerDB. The connection uses DATABASE_URL directly. There is no local state database.

`MAX_CONTEXT_ROWS` limits the initial window query; the previous continuous turn
is fetched in full without that row limit. There is no application character limit.
This demo assumes one conversation, a unique `time`
column, one worker, and one configured Pavlok device. Either speaker can trigger
that same device; no per-speaker device routing is configured.

## Removing the old column

The worker no longer reads or writes `checked`. To remove it from TigerDB, run
`migrations/002_remove_checked.sql`. This drops processing flags only and preserves
speech timestamps, contents, speaker IDs, and `ms_score`. The existing score
column stays named `ms_score`.

## Pavlok and activation log

Supply the exact Authorization header value from your
[Pavlok account](https://pavlok.readme.io/reference/intro/authentication).
The adapter uses the documented
[v5 stimulus endpoint](https://pavlok.readme.io/reference/stimulus_create_api_v5_stimulus_send_post)
with `stimulusType` read from `PAVLOK_STIMULUS_TYPE` (default `beep`), and
`stimulusValue` read from `PAVLOK_VIBRATION_STRENGTH` (default 20).
Set `PAVLOK_STIMULUS_TYPE` to the value supported by your Pavlok API/device
and restart the worker to apply it. An empty value is rejected at startup.

Each activation attempt appends a JSON record to `logs/pavlok.jsonl`, configurable
with `ACTIVATION_LOG_PATH`. It includes request time in ISO 8601 UTC, the triggering
row, current-turn rows, compared previous-turn rows, the LLM decision, and API
outcome. Each row contains `time`, `sid`, `content`, and `ms_score` as read.
`accepted` means API success, not confirmed physical vibration; `delivery_unknown`
means the request failed with uncertain delivery. Credentials are never logged.
The file contains full transcripts and is ignored by Git. An unavailable logfile
prevents activation. Cooldown skips and negative decisions don't create records.

## Azure

```bash
docker build -t speech-coach:local .
docker run --rm --env-file .env speech-coach:local
```

The generated `speech_coach.egg-info` directory is Python package metadata and
is ignored by Git.

For Azure later, use one continuously running Container App, no public ingress,
min/max replicas both 1, and environment variables backed by Azure secrets.
Container-local logfiles disappear when the container is replaced; mount/copy
them if you want to retain them. Nothing has been deployed or provisioned.

The LLM host must support OpenAI-compatible Chat Completions, system messages,
and `finish_reason=stop`.
