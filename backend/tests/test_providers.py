import json

import httpx
import pytest

from app import config, providers


@pytest.fixture(autouse=True)
def no_ambient_credentials(monkeypatch):
    """A key in the developer's own environment must not steer these tests."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(config, "LLM_PROVIDER", "")
    monkeypatch.setattr(config, "SUMMARY_MODEL", "")


def test_no_credentials_resolves_to_nothing():
    """Not an error — the report degrades to the deterministic paragraph."""
    assert providers.resolve() is None


def test_anthropic_key_is_detected(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    name, provider = providers.resolve()
    assert name == "anthropic"
    assert provider is providers.anthropic


def test_openai_key_is_detected(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert providers.resolve()[0] == "openai"


def test_anthropic_wins_when_both_keys_are_present(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert providers.resolve()[0] == "anthropic"


def test_explicit_provider_beats_detection(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
    assert providers.resolve()[0] == "openai"


def test_ollama_needs_no_key_but_must_be_named(monkeypatch):
    assert providers.resolve() is None  # never auto-detected
    monkeypatch.setattr(config, "LLM_PROVIDER", "ollama")
    assert providers.resolve()[0] == "ollama"


def test_unknown_provider_names_the_available_ones(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "gpt4all")
    with pytest.raises(providers.ProviderError) as exc:
        providers.resolve()
    assert "gpt4all" in str(exc.value)
    assert "anthropic" in str(exc.value) and "ollama" in str(exc.value)


def test_each_provider_falls_back_to_its_own_default_model():
    assert providers.model_for("openai") == providers.openai.DEFAULT_MODEL
    assert providers.model_for("ollama") == providers.ollama.DEFAULT_MODEL


def test_summary_model_overrides_every_provider(monkeypatch):
    monkeypatch.setattr(config, "SUMMARY_MODEL", "mixtral")
    assert providers.model_for("anthropic") == "mixtral"
    assert providers.model_for("ollama") == "mixtral"


# --- Ollama transport --------------------------------------------------------


def _use_transport(monkeypatch, transport: httpx.MockTransport):
    """Route the provider's client through a stub, keeping the real class."""
    real = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real(transport=transport, **kw)
    )


def _ollama_transport(captured: dict, payload: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


async def test_ollama_posts_a_chat_request_and_reads_the_message(monkeypatch):
    captured: dict = {}
    transport = _ollama_transport(
        captured, {"message": {"role": "assistant", "content": "  Grounded prose.  "}}
    )
    _use_transport(monkeypatch, transport)

    text = await providers.ollama.complete("SYS", "USER", "llama3.2")

    assert text == "Grounded prose."
    assert captured["url"] == f"{config.OLLAMA_HOST}/api/chat"
    assert captured["body"]["model"] == "llama3.2"
    assert captured["body"]["stream"] is False
    assert captured["body"]["messages"] == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "USER"},
    ]


async def test_ollama_error_propagates_so_the_summary_can_fall_back(monkeypatch):
    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    _use_transport(monkeypatch, transport)

    with pytest.raises(httpx.HTTPStatusError):
        await providers.ollama.complete("SYS", "USER", "llama3.2")


# --- OpenAI request shape ----------------------------------------------------


@pytest.fixture
def openai_capture(monkeypatch):
    """Stub the OpenAI SDK and hand back the kwargs the provider sent."""
    import sys
    from types import SimpleNamespace

    captured: dict = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            message = SimpleNamespace(content="  Grounded prose.  ")
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    def fake_client(**kwargs):
        captured["client_kwargs"] = kwargs
        return SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(AsyncOpenAI=fake_client))
    return captured


async def test_openai_sends_system_and_user_messages(openai_capture):
    text = await providers.openai.complete("SYS", "USER", "gpt-4o-mini")

    assert text == "Grounded prose."
    assert openai_capture["model"] == "gpt-4o-mini"
    assert openai_capture["messages"] == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "USER"},
    ]


async def test_openai_proper_uses_max_completion_tokens(openai_capture, monkeypatch):
    monkeypatch.setattr(config, "OPENAI_BASE_URL", "")

    await providers.openai.complete("SYS", "USER", "gpt-4o-mini")

    assert "max_completion_tokens" in openai_capture
    assert openai_capture["client_kwargs"]["base_url"] is None


async def test_compatible_endpoint_uses_max_tokens(openai_capture, monkeypatch):
    """Groq, OpenRouter, LM Studio and friends never adopted the newer field."""
    monkeypatch.setattr(config, "OPENAI_BASE_URL", "http://localhost:1234/v1")

    await providers.openai.complete("SYS", "USER", "local-model")

    assert "max_tokens" in openai_capture
    assert "max_completion_tokens" not in openai_capture
    assert openai_capture["client_kwargs"]["base_url"] == "http://localhost:1234/v1"
