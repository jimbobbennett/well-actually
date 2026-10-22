# Live speech dashboard

An 8-bit arcade-inspired live view of the `public.speech_log` TimescaleDB hypertable. The Python server keeps the database URL server-side and streams rows to the browser over Server-Sent Events; the browser polls no database credentials and stores no transcript data.

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
When `zap_sent` is true for any row in a grouped bubble, a lightning bolt appears beside it and the bubble gets an arcade-style shock pulse with a neon glow every few seconds. The bolt's border pulses in sync with the bubble.
The dashboard uses a fixed dark theme and the pixel-art zapped speech icon in the header and browser tab. Connection status remains available to screen readers without a visible live badge.
By default the server listens only on localhost. Do not expose transcript content to a network without adding appropriate authentication and transport security.

## Data handling

- `time` is treated as UTC because the existing column is a timezone-naive timestamp populated with UTC by the processing service.
- Numeric `sid` values are displayed as `Speaker N`; missing values appear as `Unassigned speaker`.
- Transcript content is rendered with `textContent` rather than HTML.
- The connection string is read from the server's `TIMESCALEDB_URL`; it is never sent to the browser.

## Container deployment

Build the server image from this directory with `docker build -t well-actually-dashboard .`. The Docker build context excludes `.env` and local development files; provide `TIMESCALEDB_URL` to the running server through a secret instead.

The Azure demo configuration is public over HTTPS and has no application login, as approved for the MVP. Do not use it for real or sensitive transcripts without adding authentication and reviewing access controls.
