from dataclasses import dataclass, field
import math
import os
from urllib.parse import urlsplit


def boolean(name: str, default: str) -> bool:
    value = os.getenv(name, default).lower()
    if value not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return value == "true"


@dataclass(frozen=True)
class Settings:
    database_url: str
    llm_url: str
    model: str
    api_key: str
    activation_log_path: str = "logs/pavlok.jsonl"
    authorization: str = ""
    strength: int = 20
    stimulus_type: str = "beep"
    confidence: float = 0.85
    cooldown: float = 120
    poll: float = 5
    context_rows: int = 200
    lookback_seconds: float = 120
    testing_mode: bool = False
    arize_api_key: str = field(default="", repr=False)
    arize_prompt_id: str = ""
    arize_prompt_label: str = ""

    @classmethod
    def from_env(cls):
        if not boolean("WEARER_OPTED_IN", "false"):
            raise ValueError("WEARER_OPTED_IN must be true")
        required = ["DATABASE_URL", "OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_API_KEY", "PAVLOK_AUTHORIZATION"]
        for name in required:
            if not os.getenv(name):
                raise ValueError(f"Missing {name}")
        prompt_mode = os.getenv("ARIZE_PROMPT_MODE", "sensitive")
        if prompt_mode not in {"original", "sensitive"}:
            raise ValueError("ARIZE_PROMPT_MODE must be original or sensitive")
        prompt_variable = f"ARIZE_PROMPT_ID_{prompt_mode.upper()}"
        prompt_id = os.getenv(prompt_variable, "")
        if not prompt_id.strip():
            raise ValueError(f"Missing {prompt_variable}")
        settings = cls(
            database_url=os.environ["DATABASE_URL"], llm_url=os.environ["OPENAI_BASE_URL"],
            model=os.environ["OPENAI_MODEL"], api_key=os.environ["OPENAI_API_KEY"],
            activation_log_path=os.getenv("ACTIVATION_LOG_PATH", "logs/pavlok.jsonl"),
            authorization=os.getenv("PAVLOK_AUTHORIZATION", ""),
            strength=int(os.getenv("PAVLOK_VIBRATION_STRENGTH", "20")),
            stimulus_type=os.getenv("PAVLOK_STIMULUS_TYPE", "beep").strip(),
            confidence=float(os.getenv("TRIGGER_CONFIDENCE", "0.85")),
            cooldown=float(os.getenv("COOLDOWN_SECONDS", "120")),
            poll=float(os.getenv("POLL_SECONDS", "5")),
            context_rows=int(os.getenv("MAX_CONTEXT_ROWS", "200")),
            lookback_seconds=float(os.getenv("LOOKBACK_SECONDS", "120")),
            testing_mode=boolean("TESTING_MODE", "false"),
            arize_api_key=os.getenv("ARIZE_API_KEY", ""),
            arize_prompt_id=prompt_id,
            arize_prompt_label=os.getenv("ARIZE_PROMPT_LABEL", ""),
        )
        if urlsplit(settings.llm_url).scheme != "https" or urlsplit(settings.llm_url).username:
            raise ValueError("OPENAI_BASE_URL must use HTTPS without embedded credentials")
        for value in (settings.cooldown, settings.poll, settings.lookback_seconds, settings.confidence):
            if not math.isfinite(value) or value <= 0:
                raise ValueError("Intervals and confidence must be finite and positive")
        if not 0 < settings.confidence <= 1 or not 1 <= settings.strength <= 100:
            raise ValueError("Invalid confidence or vibration strength")
        if settings.context_rows < 3:
            raise ValueError("Invalid context limits")
        if not settings.authorization:
            raise ValueError("Pavlok authorization is required")
        if not settings.stimulus_type:
            raise ValueError("PAVLOK_STIMULUS_TYPE must not be empty")
        if not settings.arize_api_key or not settings.arize_prompt_id:
            raise ValueError("ARIZE_API_KEY and the selected prompt ID are required for prompt management")
        return settings
