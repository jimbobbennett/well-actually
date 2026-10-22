"""FastAPI server for the live TimescaleDB speech-log dashboard."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from psycopg import AsyncConnection
from psycopg.rows import dict_row

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
INITIAL_LIMIT = 80
POLL_INTERVAL_SECONDS = 1
HEARTBEAT_INTERVAL_SECONDS = 15
CONNECT_TIMEOUT_SECONDS = 5

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("speech_dashboard")
load_dotenv(APP_DIR / ".env")

app = FastAPI(title="Well Actually Live Speech")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def database_url() -> str:
    value = os.environ.get("TIMESCALEDB_URL")
    if not value:
        raise HTTPException(
            status_code=503,
            detail="Set TIMESCALEDB_URL on the dashboard server.",
        )
    return value


def parse_cursor(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid speech-log cursor.") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def serialize_record(row: dict[str, Any]) -> dict[str, Any]:
    event_time = row["time"]
    if event_time.tzinfo is not None:
        event_time = event_time.astimezone(timezone.utc).replace(tzinfo=None)
    return {
        "time": event_time.isoformat(timespec="microseconds"),
        "sid": row["sid"],
        "content": row["content"] or "",
        "ms_score": row["ms_score"],
    }


def encode_sse(event: str, data: dict[str, Any], event_id: str | None = None) -> str:
    message = ""
    if event_id is not None:
        message += f"id: {event_id}\n"
    message += f"event: {event}\n"
    message += f"data: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"
    return message


async def fetch_latest(cursor, limit: int) -> list[dict[str, Any]]:
    await cursor.execute(
        'SELECT "time", "sid", "content", "ms_score" '
        "FROM public.speech_log ORDER BY \"time\" DESC LIMIT %s",
        (limit,),
    )
    return await cursor.fetchall()


async def fetch_after(cursor, after: datetime) -> list[dict[str, Any]]:
    await cursor.execute(
        'SELECT "time", "sid", "content", "ms_score" '
        'FROM public.speech_log WHERE "time" > %s ORDER BY "time" ASC LIMIT 500',
        (after,),
    )
    return await cursor.fetchall()


async def speech_events(
    request: Request,
    dsn: str,
    initial_cursor: datetime | None,
) -> Any:
    cursor_time = initial_cursor
    last_heartbeat = time.monotonic()
    try:
        connection = await AsyncConnection.connect(
            dsn,
            connect_timeout=CONNECT_TIMEOUT_SECONDS,
            autocommit=True,
            row_factory=dict_row,
        )
        async with connection:
            async with connection.cursor() as cursor:
                if cursor_time is None:
                    rows = await fetch_latest(cursor, INITIAL_LIMIT)
                    rows.reverse()
                    for row in rows:
                        record = serialize_record(row)
                        cursor_time = datetime.fromisoformat(record["time"])
                        yield encode_sse("speech", record, record["time"])
                    yield encode_sse("connected", {"initial_count": len(rows)})
                else:
                    yield encode_sse("connected", {"initial_count": 0})

                while not await request.is_disconnected():
                    rows = (
                        await fetch_after(cursor, cursor_time)
                        if cursor_time is not None
                        else await fetch_latest(cursor, INITIAL_LIMIT)
                    )
                    if cursor_time is None:
                        rows.reverse()
                    for row in rows:
                        record = serialize_record(row)
                        cursor_time = datetime.fromisoformat(record["time"])
                        yield encode_sse("speech", record, record["time"])

                    current_time = time.monotonic()
                    if current_time - last_heartbeat >= HEARTBEAT_INTERVAL_SECONDS:
                        yield ": keep-alive\n\n"
                        last_heartbeat = current_time
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
    except psycopg.Error as exc:
        LOGGER.error("Speech dashboard database stream failed: %s", type(exc).__name__)
        yield encode_sse(
            "dashboard-error",
            {"message": "Database connection interrupted. The dashboard will reconnect."},
        )


@app.get("/", response_class=FileResponse)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict[str, str]:
    dsn = database_url()
    try:
        connection = await AsyncConnection.connect(
            dsn,
            connect_timeout=CONNECT_TIMEOUT_SECONDS,
            autocommit=True,
        )
        async with connection:
            await connection.execute("SELECT 1")
    except psycopg.Error as exc:
        LOGGER.error("Speech dashboard health check failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="TimescaleDB is unavailable.") from exc
    return {"status": "ok"}


@app.get("/api/speech-log/stream")
async def stream_speech_log(
    request: Request,
    after: str | None = Query(default=None),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    try:
        initial_cursor = parse_cursor(after or last_event_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return StreamingResponse(
        speech_events(request, database_url(), initial_cursor),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
