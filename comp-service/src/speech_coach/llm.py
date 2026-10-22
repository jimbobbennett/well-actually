from dataclasses import dataclass, field
import json
import math
import logging

from openai import OpenAI
from .prompts import load_prompt

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class Decision:
    condescending: bool
    reexplaining: bool
    confidence: float
    tone: str | None = None
    tone_evidence: list[str] = field(default_factory=list)

    @classmethod
    def parse(cls, content):
        value = json.loads(content)
        base_fields = {"condescending", "reexplaining", "confidence"}
        tone_fields = {"tone", "tone_evidence"}
        if not isinstance(value, dict) or set(value) not in (base_fields, base_fields | tone_fields):
            raise ValueError("Unexpected decision fields")
        if any(type(value[k]) is not bool for k in ("condescending", "reexplaining")):
            raise ValueError("Decision flags must be booleans")
        confidence = value["confidence"]
        if type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("Invalid decision confidence")
        if "tone" in value:
            tone = value["tone"]
            evidence = value["tone_evidence"]
            if not isinstance(tone, str) or not tone.strip() or len(tone) > 200:
                raise ValueError("Invalid tone assessment")
            if (not isinstance(evidence, list) or len(evidence) > 5
                    or any(not isinstance(item, str) or not item.strip() or len(item) > 500
                           for item in evidence)):
                raise ValueError("Invalid tone evidence")
        return cls(**value)

    def triggers(self, threshold):
        return (self.condescending or self.reexplaining) and self.confidence >= threshold


class Classifier:
    def __init__(self, settings):
        self.model = settings.model
        self.prompt = load_prompt(settings)
        self.client = OpenAI(base_url=settings.llm_url, api_key=settings.api_key,
                             timeout=30, max_retries=0)

    def evaluate(self, context):
        request = {
            "model": self.model,
            "messages": self.prompt.render(json.dumps(context.payload(), ensure_ascii=False)),
        }
        response = self.client.chat.completions.create(**request)
        if not response.choices or response.choices[0].finish_reason != "stop":
            LOG.error("LLM response incomplete: choices=%s; finish_reason=%s",
                      len(response.choices), response.choices[0].finish_reason if response.choices else None)
            raise ValueError("Incomplete model decision")
        try:
            return Decision.parse(response.choices[0].message.content)
        except (ValueError, TypeError) as error:
            LOG.error("LLM decision parse failed: error_type=%s; response content omitted",
                      type(error).__name__)
            raise

    def close(self):
        self.client.close()
