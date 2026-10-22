# Processing service

Python starter package for the Arduino UNO Q audio processing service. The UNO Q runs Linux, so this service is intended to run as a Linux process; audio capture and Edge Impulse integration still need to be verified on the actual hardware.

## Responsibilities

- Capture audio from the eMeet 10 on the UNO Q.
- Stream audio to Azure Speech and normalize finalized diarized segments.
- Persist finalized segments to Tiger Data TimescaleDB.
- Run local wake-word detection independently from cloud transcription.
- Send wake-word events to the future API once its contract is available.

Keep these integrations behind small modules/interfaces so contributors can work independently and test with fakes before hardware or credentials are available. Do not commit credentials, local `.env` files, or raw audio.

## Layout

```text
processing-service/
├── README.md                      # Development and deployment notes
├── pyproject.toml                 # Package metadata and build configuration
├── .env.example                   # Placeholder configuration names; no real secrets
├── .gitignore                     # Local environments and secrets
├── deploy/                        # UNO Q deployment script and systemd user-unit template
├── src/well_actually_processing/  # Installable package, audio capture, and processing service
├── unoq-led-indicator/            # UNO Q microphone icon animation app
└── tests/                         # Fast tests that do not need hardware or cloud access
```

As implementation is added, keep boundaries clear within `well_actually_processing`:

- `audio`: microphone capture and audio format handling
- `speech`: Azure Speech client and transcript normalization
- `persistence`: PostgreSQL/TimescaleDB writes and migrations
- `wake_word`: Edge Impulse integration and local detection events
- `events`: future API client and event contract

Add tests alongside each behavior. Keep hardware/cloud calls at the edges so unit tests can use fakes.

## Development

Use Python 3.10 or newer. Create an isolated environment and install the package in editable mode:

```sh
cd processing-service
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[service]"
```

Run the hardware/cloud-independent tests with:

```sh
python -m unittest discover -s tests
```

## Microphone capture

The capture utility uses ALSA's `arecord` command, supplied by `alsa-utils` on Debian. On the UNO Q, list available inputs first:

```sh
~/well-actually-processing/.venv/bin/well-actually-capture --list-devices
```

Record a short bounded WAV sample. Captures are ignored by Git:

```sh
~/well-actually-processing/.venv/bin/well-actually-capture \
  --device hw:CARD=M0,DEV=0 --sample-rate 16000 --channels 1 \
  --output captures/emeet-test.wav --duration-seconds 5
```

On the connected UNO Q, ALSA enumerated the microphone as `eMeet M0` (`hw:CARD=M0,DEV=0`); a 30-second test succeeded at 16 kHz, mono, 16-bit PCM. The temporary WAV was removed after validation. Use `--device`, `--sample-rate`, and `--channels` to match the formats reported by ALSA if the hardware setup changes. The defaults remain initial settings, not a guarantee for other devices.

## Azure Speech streaming smoke test

The smoke test streams raw ALSA PCM directly into Azure Speech using the Python Speech SDK `PushAudioInputStream` and `ConversationTranscriber`. It prints finalized text, timestamps, and temporary speaker IDs to the terminal; it does not save audio or transcripts.

Set `AZURE_SPEECH_ENDPOINT`, `AZURE_SPEECH_KEY`, and `AZURE_SPEECH_LANGUAGE`, then run:

```sh
well-actually-speech-smoke --device hw:CARD=M0,DEV=0 --duration-seconds 30
```

The smoke test remains available with `well-actually-speech-smoke`; the continuously running service uses the `service` extra, which also installs the PostgreSQL driver.

## Continuous speech logging

The systemd user service captures ALSA PCM continuously, streams it to Azure Speech, maps `Guest-N` speaker labels to integer `sid=N`, and inserts finalized recognized speech into `public.speech_log`. It stores the segment's UTC start time as a timezone-naive UTC value because the table's `time` column has no timezone, writes the recognized text to `content`, and inserts `NULL` for `ms_score`. Missing/unrecognized speaker labels are stored as `NULL`.

The service starts the Arduino App Lab LED indicator app before recording. Its LED matrix pulses a microphone icon until the service stops. Deploy the package, then create `~/.config/well-actually-processing/service.env` on the UNO Q with `AZURE_SPEECH_ENDPOINT`, `AZURE_SPEECH_KEY`, `AZURE_SPEECH_LANGUAGE`, and `TIMESCALEDB_URL`; restrict it with `chmod 600`. The deploy script does not transfer `.env` files.

Start and stop the service remotely with:

```sh
ssh arduino@<uno-q-host> 'systemctl --user start well-actually-processing.service'
ssh arduino@<uno-q-host> 'systemctl --user stop well-actually-processing.service'
```

The unit restarts on service failures but is not enabled to start automatically at device boot. Stopping it terminates audio capture, closes the Azure stream, and stops the matrix indicator.

Before submitting a change, run the tests and describe any hardware or cloud validation that could not be performed. Keep pull requests focused on one component or contract at a time, and update this README when the package layout or setup changes.

## Configuration and secrets

Copy `.env.example` to `.env` for local configuration. The systemd service reads its settings from its environment file; the deploy script does not copy local `.env` files. Do not put provider keys, database passwords, or API tokens in source files or committed configuration; only placeholder values belong in committed examples. On the UNO Q, store the systemd environment file at `~/.config/well-actually-processing/service.env` and restrict it to the service user (`chmod 600`).

## Deploying to an UNO Q

The UNO Q must have Python 3.10+, `python3-venv`, `alsa-utils`, Arduino App Lab, and SSH enabled; it must be reachable from the development machine. Install the OS-provided packages on the board first if they are missing. The deploy script uses the development machine's `tar` and `ssh` commands to transfer the package. From this directory, deploy with:

```sh
UNO_HOST=uno@192.168.1.42 ./deploy/deploy-to-uno.sh
```

The script transfers this folder to `~/well-actually-processing`, excluding local secrets, audio captures, and development-only files, then creates a virtual environment and installs the Speech SDK and PostgreSQL driver. It installs the systemd unit but does not copy `.env` or start the service.

Create its mode-600 environment file before starting the service. Use `systemctl --user enable --now well-actually-processing.service` only if it should also start automatically at device boot; enable user lingering if it must run without an interactive login.
