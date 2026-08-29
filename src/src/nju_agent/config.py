from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"
    max_steps: int = 8
    context_token_limit: int = 96000
    recent_turns: int = 4


def load_settings(env: dict[str, str] | None = None) -> Settings:
    data = os.environ if env is None else env

    api_key = (
        data.get("DEEPSEEK_API_KEY", "").strip()
        or data.get("OPENAI_API_KEY", "").strip()
    )
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is required")

    base_url = (
        data.get("DEEPSEEK_BASE_URL", "").strip()
        or data.get("OPENAI_BASE_URL", "").strip()
        or "https://api.deepseek.com"
    )
    model = (
        data.get("DEEPSEEK_MODEL", "").strip()
        or data.get("OPENAI_MODEL", "").strip()
        or "deepseek-v4-flash"
    )

    max_steps_raw = data.get("NJU_AGENT_MAX_STEPS", "").strip()
    max_steps = int(max_steps_raw) if max_steps_raw else 8

    context_token_limit_raw = data.get("NJU_AGENT_CONTEXT_TOKEN_LIMIT", "").strip()
    context_token_limit = int(context_token_limit_raw) if context_token_limit_raw else 96000

    recent_turns_raw = data.get("NJU_AGENT_RECENT_TURNS", "").strip()
    recent_turns = int(recent_turns_raw) if recent_turns_raw else 4

    return Settings(
        api_key=api_key,
        base_url=base_url,
        model=model,
        max_steps=max_steps,
        context_token_limit=context_token_limit,
        recent_turns=recent_turns,
    )
