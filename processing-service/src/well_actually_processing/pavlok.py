"""Send phrase-detected vibe requests to the Pavlok API."""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_PAVLOK_API_URL = "https://api.pavlok.com/api/v5/stimulus/send"
DEFAULT_VIBE_VALUE = 50
REQUEST_TIMEOUT_SECONDS = 5


class PavlokClientError(RuntimeError):
    """Raised when the Pavlok API does not accept a vibe request."""


class PavlokClient:
    def __init__(
        self,
        token: str,
        api_url: str = DEFAULT_PAVLOK_API_URL,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        if not token.strip():
            raise ValueError("A Pavlok API token is required.")
        if not api_url.startswith("https://"):
            raise ValueError("The Pavlok API URL must use HTTPS.")
        self._token = token.strip()
        self._api_url = api_url
        self._timeout = timeout

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
        return cls(
            token=token,
            api_url=api_url,
        )

    def send_vibe(self) -> None:
        body = json.dumps(
            {
                "stimulus": {
                    "stimulusType": "vibe",
                    "stimulusValue": DEFAULT_VIBE_VALUE,
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
