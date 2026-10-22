# Live speech dashboard

A bright, chat-style live view of the `public.speech_log` TimescaleDB hypertable. The Python server keeps the database URL server-side and streams rows to the browser over Server-Sent Events; the browser polls no database credentials and stores no transcript data.

## Run locally

Use Python 3.10 or newer:

```sh
cd web-app
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Set `TIMESCALEDB_URL` in `.env` to the Tiger Cloud PostgreSQL URI with TLS enabled, then launch the app:

```sh
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. The dashboard loads the latest 80 speech rows and then polls the database once per second through a single SSE connection. It reconnects automatically after an interrupted stream. The recorder must be running to produce new rows; the dashboard does not start or stop audio capture.

Consecutive rows from the same speaker are grouped into one chat bubble, with each transcript segment on a new line.
When `zap_sent` is true for any row in a grouped bubble, a lightning bolt appears beside that bubble.
The dashboard defaults to the luminous dark theme. Use the header toggle to switch to the bright light theme; your preference is saved in the browser.
By default the server listens only on localhost. Do not expose transcript content to a network without adding appropriate authentication and transport security.

## Data handling

- `time` is treated as UTC because the existing column is a timezone-naive timestamp populated with UTC by the processing service.
- Numeric `sid` values are displayed as `Speaker N`; missing values appear as `Unassigned speaker`.
- Transcript content is rendered with `textContent` rather than HTML.
- The connection string is read from the server's `TIMESCALEDB_URL`; it is never sent to the browser.
