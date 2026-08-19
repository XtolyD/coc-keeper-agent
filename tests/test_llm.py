# -*- coding: utf-8 -*-
from types import SimpleNamespace

from coc_keeper.agent.llm import LLMClient
from coc_keeper.config import GrokVisionSettings, Settings, _openai_base_url


def test_llm_client_captures_reasoning_content():
    message = SimpleNamespace(
        content=None,
        reasoning_content="需要调用一次检定工具。",
        model_extra={},
        tool_calls=[SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(name="roll_skill_check", arguments='{"skill":"潜行"}'),
        )],
    )
    completion = SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
    )
    client = object.__new__(LLMClient)
    client.settings = Settings(api_key="test", base_url="https://example.invalid", model="stub")
    client.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: completion)),
    )

    response = client.chat([{"role": "user", "content": "隐藏起来"}], tools=[{"type": "function"}])

    assert response.reasoning_content == "需要调用一次检定工具。"
    assert response.tool_calls[0]["name"] == "roll_skill_check"


def test_grok_vision_settings_default_to_45(monkeypatch):
    monkeypatch.delenv("GROK_MODEL", raising=False)
    monkeypatch.setenv("GROK_API", "https://example.invalid/v1")
    monkeypatch.setenv("GROK_API_KEY", "test-key")
    settings = GrokVisionSettings()
    assert settings.model == "grok-4.5"
    assert settings.is_configured is True


def test_openai_base_url_normalizes_provider_origin_and_full_endpoint():
    assert _openai_base_url("https://example.invalid") == "https://example.invalid/v1"
    assert _openai_base_url("https://example.invalid/v1") == "https://example.invalid/v1"
    assert _openai_base_url("https://example.invalid/v1/chat/completions") == "https://example.invalid/v1"
