import pytest

from nju_agent.config import load_settings


def test_load_settings_reads_environment_values() -> None:
    settings = load_settings(
        {
            "DEEPSEEK_API_KEY": "key-123",
            "DEEPSEEK_BASE_URL": "https://example.com/v1",
            "DEEPSEEK_MODEL": "deepseek-test",
            "NJU_AGENT_MAX_STEPS": "12",
        }
    )

    assert settings.api_key == "key-123"
    assert settings.base_url == "https://example.com/v1"
    assert settings.model == "deepseek-test"
    assert settings.max_steps == 12
    assert settings.context_token_limit == 96000
    assert settings.recent_turns == 4


def test_load_settings_requires_api_key() -> None:
    with pytest.raises(RuntimeError):
        load_settings({})
