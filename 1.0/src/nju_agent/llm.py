from __future__ import annotations

from typing import Any

from openai import OpenAI

from .config import Settings


def build_client(settings: Settings) -> OpenAI:
    client_kwargs: dict[str, Any] = {"api_key": settings.api_key}
    if settings.base_url:
        client_kwargs["base_url"] = settings.base_url
    return OpenAI(**client_kwargs)


def request_response(
    client: OpenAI,
    *,
    model: str,
    input: Any,
    tools: list[dict[str, Any]],
    instructions: str,
) -> Any:
    request_kwargs: dict[str, Any] = {
        "model": model,
        "input": input,
        "tools": tools,
        "instructions": instructions,
    }

    return client.responses.create(**request_kwargs)
