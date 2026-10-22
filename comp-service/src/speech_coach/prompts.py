from dataclasses import dataclass
from string import Formatter
from urllib.parse import quote

import httpx


@dataclass(frozen=True)
class ManagedPrompt:
    version_id: str
    label: str
    templates: tuple[tuple[str, str], ...]

    def render(self, conversation_json):
        return [
            {"role": role, "content": content.format(conversation_json=conversation_json)}
            for role, content in self.templates
        ]


def load_prompt(settings):
    """Resolve once at startup; invalid or unavailable prompts stop the worker."""
    label = settings.arize_prompt_label or ("staging" if settings.testing_mode else "production")
    url = ("https://api.arize.com/v2/prompts/"
           f"{quote(settings.arize_prompt_id, safe='')}/labels/{quote(label, safe='')}")
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        response = client.get(url, headers={
            "Authorization": f"Bearer {settings.arize_api_key}",
            "Accept": "application/json",
        })
        response.raise_for_status()
        version = response.json()
    if version.get("input_variable_format") != "F_STRING":
        raise ValueError("Managed prompt must use F_STRING templates")
    version_id = version.get("id")
    if not isinstance(version_id, str) or not version_id:
        raise ValueError("Managed prompt version ID is missing")
    messages = version.get("messages")
    if not isinstance(messages, list) or len(messages) != 2:
        raise ValueError("Managed prompt must contain one system and one user message")
    templates = []
    variables = set()
    for message, expected_role in zip(messages, ("SYSTEM", "USER")):
        if not isinstance(message, dict) or message.get("role") != expected_role:
            raise ValueError("Unexpected managed prompt role")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Managed prompt message is empty")
        for _, name, spec, conversion in Formatter().parse(content):
            if name is not None:
                if name != "conversation_json" or spec or conversion:
                    raise ValueError("Unsupported managed prompt variable")
                variables.add(name)
        templates.append((expected_role.lower(), content))
    if variables != {"conversation_json"}:
        raise ValueError("Managed prompt must include conversation_json")
    return ManagedPrompt(version_id, label, tuple(templates))
