import pytest

from nju_agent.config import load_settings


def test_load_settings_reads_environment_values() -> None:
    settings = load_settings(
        {
            "OPENAI_API_KEY": "key-123",
            "OPENAI_BASE_URL": "https://example.com/v1",
            "OPENAI_MODEL": "gpt-test",
            "NJU_AGENT_MAX_STEPS": "12",
        }
    )

    assert settings.api_key == "key-123"
    assert settings.base_url == "https://example.com/v1"
    assert settings.model == "gpt-test"
    assert settings.max_steps == 12


def test_load_settings_requires_api_key() -> None:
    with pytest.raises(RuntimeError):
        load_settings({})
