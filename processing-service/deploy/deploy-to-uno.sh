#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${UNO_HOST:-}" ]]; then
  echo "Set UNO_HOST to the SSH target, for example uno@192.168.1.42." >&2
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
service_dir="$(cd -- "${script_dir}/.." && pwd)"

COPYFILE_DISABLE=1 tar -czf - \
  --exclude='.env*' \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='.ruff_cache' \
  --exclude='tests' \
  --exclude='captures' \
  --exclude='*.wav' \
  -C "${service_dir}" . \
  | ssh "${UNO_HOST}" \
    'set -e; mkdir -p "$HOME/well-actually-processing" "$HOME/.config/systemd/user" "$HOME/.config/well-actually-processing"; chmod 700 "$HOME/.config/well-actually-processing"; tar -xzf - -C "$HOME/well-actually-processing"; cd "$HOME/well-actually-processing"; python3 -m venv .venv; .venv/bin/python -m pip install --upgrade pip; .venv/bin/python -m pip install ".[service]"; cp deploy/well-actually-processing.service "$HOME/.config/systemd/user/well-actually-processing.service"; systemctl --user daemon-reload'

echo "Package staged on ${UNO_HOST}:~/well-actually-processing"
echo "The systemd unit is installed but the service is not started; configure service.env first."
