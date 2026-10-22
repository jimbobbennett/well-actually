# Audio processing service implementation plan

**Status:** In progress

**Azure resource group:** `rg_well_actually` in `westus2` (created)
**Tiger Data service:** `speechlog_db_service` (`fnd4by4qau`, TimescaleDB, `us-east-1`, READY)

## Goal

Capture audio from the eMeet 10 on an Arduino UNO Q, stream it to Azure Speech for transcription and speaker diarization, and write finalized diarized segments to Tiger Data TimescaleDB. Independently, detect a small set of wake words on the UNO Q with an Arduino Edge Impulse-trained block and emit an event to an API whose contract will be supplied later.

## Checklist

### Azure and Tiger Data setup

- [x] Create Azure resource group `rg_well_actually` in `westus2`.
- [x] Confirm Azure CLI authentication to the Visual Studio Enterprise subscription.
- [x] List Tiger Cloud services and confirm `speechlog_db_service` is READY.
- [x] Capture the Tiger service's PostgreSQL connection details in the ignored `.env` file and verify access with a read-only `SELECT 1`.
- [x] Provision the Azure AI Speech resource in the resource group.
- [x] Configure the Speech endpoint, key, and language in the ignored `processing-service/.env` file.
- [ ] Confirm the target language and expected diarization behavior with a representative audio sample.

### Device and processing service

- [x] Create a collaborative Python package scaffold in `processing-service/`.
- [x] Add a placeholder-only `.env.example` and ignore local `.env` files.
- [x] Add an SSH/tar deployment script and systemd user-unit template for the UNO Q.
- [x] Build a Python CLI to list ALSA capture devices and record a bounded WAV sample.
- [x] Connect the eMeet microphone and verify Linux detects it as `eMeet M0` (`hw:CARD=M0,DEV=0`).
- [x] Inspect supported format and capture a short sample: 16 kHz, mono, 16-bit PCM; 3-second WAV validated.
- [x] Confirm continuous capture is sustainable with a 30-second recording.
- [x] Add an optional Azure Speech SDK dependency and bounded streaming smoke-test CLI that prints finalized text, timestamps, and speaker IDs without saving audio or transcripts.
- [x] Run a 30-second live eMeet-to-Azure stream on the UNO Q; Azure returned seven finalized segments labeled across two speakers.
- [x] Define an audio-session lifecycle, supported PCM format, reconnect behavior, and environment-based Speech/database configuration.
- [x] Implement the continuously running UNO Q Python service that streams microphone audio to Azure Speech.
- [x] Handle finalized recognition separately; persist only finalized segments.
- [x] Map `Guest-N` to integer `sid=N`, use the UTC audio offset for `time`, store recognized text in `content`, and write `NULL` to `ms_score`; missing speaker IDs remain `NULL`.
- [x] Add a pulsing microphone icon on the UNO Q LED matrix while the service runs.

### TimescaleDB persistence

- [x] Use the existing `speech_log` TimescaleDB hypertable and confirm the required column types.
- [x] Select psycopg 3 and insert each finalized segment with parameterized SQL.
- [x] Add bounded insert retries and explicit error logging for transient database failures.
- [x] Confirm the service does not retain raw audio.

### Local wake word and future API

- [ ] Confirm the wake-word set and matching trained Arduino Edge Impulse block/model.
- [ ] Integrate local wake-word detection independently from Azure transcription.
- [ ] Emit a wake-word event with session ID, detected word/class, and timestamp; tune repeated-detection behavior for the model.
- [ ] Obtain the future API contract and credentials.
- [ ] Implement the API client behind an event adapter, keeping credentials outside source control.

### End-to-end validation

- [ ] Test device capture, Azure transcription/diarization, and persisted timestamps/speaker labels with a representative, consented sample audio.
- [ ] Test database failure reporting and retry behavior.
- [ ] Test wake-word true/false detections and API-event delivery.
- [x] Verify the systemd user service starts and stops cleanly and the LED indicator follows its lifecycle.
- [ ] Enable automatic startup at device boot if required.

## Current prerequisites and boundaries

- **Done:** created Azure resource group `rg_well_actually` in `westus2`.
- **Done:** Azure AI Speech resource and its endpoint/key/language configuration are set up in the local ignored `.env`.
- **Done:** rotated the Speech key after it was exposed in a command result; the replacement is in the local ignored `.env` and the UNO Q's mode-600 smoke-test environment file.
- **Done:** a live 30-second smoke test streamed eMeet audio to Azure and printed seven finalized diarized segments; no audio or transcript was saved by the smoke-test utility.
- **Done:** verified `public.speech_log` is a TimescaleDB hypertable with `time TIMESTAMP`, nullable integer `sid`, text `content`, and nullable integer `ms_score`.
- **Done:** the running UNO Q service wrote 10 live speech segments; recent rows had UTC timestamps, integer speaker IDs, and `NULL` `ms_score`.
- **Done:** verified that stopping the systemd unit stops the LED matrix app, and starting it again restarts both.
- **Done:** listed Tiger Cloud services; `speechlog_db_service` is READY in `us-east-1`.
- **Done:** Tiger connection details are in the ignored `.env`; Python read-only `SELECT 1` succeeded.
- **Available:** Azure CLI is installed and authenticated to the Visual Studio Enterprise subscription.
- **Available:** Tiger CLI and Tiger MCP are installed and authenticated/configured.
- **Waiting:** accuracy validation of the chosen language and diarization behavior with a representative, consented audio sample.
- **Waiting:** wake-word set and the matching trained Edge Impulse block/model.
- **Waiting:** future wake-word API contract and credentials.
- **Runtime note:** the service will use PostgreSQL directly; Tiger CLI/MCP are for management and development access.
- **Hardware check:** UNO Q host `llm-test` sees eMeet M0; 3-second and 30-second WAV captures passed validation at 16 kHz mono, 16-bit PCM. Temporary audio files were deleted after validation.
- **Not included yet:** local wake-word detection and wake-word API integration. Automatic startup at device boot is not enabled.
