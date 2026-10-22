"""Send phrase-detected stimuli to the Pavlok API."""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_PAVLOK_API_URL = "https://api.pavlok.com/api/v5/stimulus/send"
DEFAULT_STIMULUS_TYPE = "beep"
DEFAULT_STIMULUS_LEVEL = 50
ALLOWED_STIMULUS_TYPES = frozenset({"zap", "beep", "vibe"})
MIN_STIMULUS_LEVEL = 1
MAX_STIMULUS_LEVEL = 100
REQUEST_TIMEOUT_SECONDS = 5


class PavlokClientError(RuntimeError):
    """Raised when the Pavlok API does not accept a stimulus request."""


class PavlokClient:
    def __init__(
        self,
        token: str,
        api_url: str = DEFAULT_PAVLOK_API_URL,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
        stimulus_type: str = DEFAULT_STIMULUS_TYPE,
        stimulus_level: int = DEFAULT_STIMULUS_LEVEL,
    ) -> None:
        if not token.strip():
            raise ValueError("A Pavlok API token is required.")
        if not api_url.startswith("https://"):
            raise ValueError("The Pavlok API URL must use HTTPS.")
        stimulus_type = stimulus_type.strip().casefold()
        if stimulus_type not in ALLOWED_STIMULUS_TYPES:
            allowed_types = ", ".join(sorted(ALLOWED_STIMULUS_TYPES))
            raise ValueError(f"Pavlok stimulus type must be one of: {allowed_types}.")
        if (
            isinstance(stimulus_level, bool)
            or not isinstance(stimulus_level, int)
            or not MIN_STIMULUS_LEVEL <= stimulus_level <= MAX_STIMULUS_LEVEL
        ):
            raise ValueError(
                f"Pavlok stimulus level must be between {MIN_STIMULUS_LEVEL} "
                f"and {MAX_STIMULUS_LEVEL}."
            )
        self._token = token.strip()
        self._api_url = api_url
        self._timeout = timeout
        self._stimulus_type = stimulus_type
        self._stimulus_level = stimulus_level

    @classmethod
    def from_environment(cls) -> PavlokClient | None:
        token = os.environ.get("WAKE_WORD_API_TOKEN")
        if not token or not token.strip() or token.strip().startswith("replace-"):
            token = os.environ.get("PAVLOCK_API_KEY") or os.environ.get(
                "PAVLOK_API_KEY"
            )
        if not token or not token.strip():
            return None
        api_url = os.environ.get("WAKE_WORD_API_URL", DEFAULT_PAVLOK_API_URL)
        if not api_url or api_url.startswith("replace-"):
            api_url = DEFAULT_PAVLOK_API_URL
        stimulus_type = os.environ.get(
            "PAVLOK_STIMULUS_TYPE",
            DEFAULT_STIMULUS_TYPE,
        )
        level_value = os.environ.get(
            "PAVLOK_STIMULUS_LEVEL",
            str(DEFAULT_STIMULUS_LEVEL),
        )
        try:
            stimulus_level = int(level_value)
        except ValueError as exc:
            raise ValueError(
                "PAVLOK_STIMULUS_LEVEL must be an integer from 1 to 100."
            ) from exc
        return cls(
            token=token,
            api_url=api_url,
            stimulus_type=stimulus_type,
            stimulus_level=stimulus_level,
        )

    def send_stimulus(self) -> None:
        body = json.dumps(
            {
                "stimulus": {
                    "stimulusType": self._stimulus_type,
                    "stimulusValue": self._stimulus_level,
                }
            }
        ).encode("utf-8")
        request = Request(
            self._api_url,
            data=body,
            headers={
                "Authorization": self._token,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                if not 200 <= response.status < 300:
                    raise PavlokClientError(
                        f"Pavlok API returned HTTP {response.status}."
                    )
        except HTTPError as exc:
            raise PavlokClientError(
                f"Pavlok API returned HTTP {exc.code}."
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise PavlokClientError("Could not reach the Pavlok API.") from exc
