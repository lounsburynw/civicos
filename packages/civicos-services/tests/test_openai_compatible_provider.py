"""
Tests for openai_compatible_provider.py — OpenAI-compatible LLM providers.

Covers construction defaults, env-var fallbacks, explicit-arg overrides, and
provider-specific logic (PerplexityProvider delegation, OpenRouter header
injection). The OpenAI SDK client is mocked at the class boundary; the logic
under test (OpenAICompatibleProvider and its subclasses) is never mocked.

To run:
    pytest packages/civicos-services/tests/test_openai_compatible_provider.py \
        -q --override-ini="addopts="
"""

import os
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

from civicos_services.providers.base import CompletionResponse
from civicos_services.providers.openai_compatible_provider import (
    GroqProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    OpenRouterProvider,
    PerplexityProvider,
)


# ---------------------------------------------------------------------------
# Env-var helpers
# ---------------------------------------------------------------------------

PROVIDER_ENV_VARS = (
    "GROQ_API_KEY",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "PERPLEXITY_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "OPENROUTER_APP_NAME",
    "OPENROUTER_SITE_URL",
)


def _isolate_env(**overrides):
    """
    Return a patch.dict context that starts from a clean slate for
    provider-related env vars, then applies any overrides.

    Using clear=False preserves PATH and other unrelated vars; we then
    explicitly drop only the provider keys and set the overrides.
    """
    patcher = patch.dict(os.environ, {}, clear=False)
    patcher.start()
    for key in PROVIDER_ENV_VARS:
        os.environ.pop(key, None)
    for k, v in overrides.items():
        os.environ[k] = v
    return patcher


# ---------------------------------------------------------------------------
# Mock response helpers
# ---------------------------------------------------------------------------

def _patch_openai_client():
    """Patch the OpenAI class inside openai_compatible_provider."""
    return patch("civicos_services.providers.openai_compatible_provider.OpenAI")


def _make_chat_response(content="response text",
                        finish_reason="stop",
                        prompt_tokens=5,
                        completion_tokens=10):
    """
    Build a minimal object matching the shape OpenAIProvider.complete() reads:
        response.choices[0].message.content
        response.choices[0].message.tool_calls   (None → no tool calls)
        response.choices[0].finish_reason
        response.usage.prompt_tokens
        response.usage.completion_tokens
        response.usage.total_tokens

    SimpleNamespace gives us real attribute access (unlike MagicMock which
    auto-creates attributes and returns MagicMock objects everywhere).
    """
    message = SimpleNamespace(content=content, tool_calls=None)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )
    return SimpleNamespace(choices=[choice], usage=usage)


def _build_provider(provider_cls, env=None, **kwargs):
    """
    Construct a provider with env isolation + OpenAI client mocked.
    Returns (provider, mock_client, mock_openai_cls). mock_openai_cls stays
    valid after the patch context exits because it is the MagicMock object
    we return, not the patched attribute.
    """
    env = env or {}
    patcher = _isolate_env(**env)
    try:
        with _patch_openai_client() as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            provider = provider_cls(**kwargs)
            return provider, mock_client, mock_cls
    finally:
        patcher.stop()


# ===========================================================================
# OpenAICompatibleProvider — base class
# ===========================================================================

class TestOpenAICompatibleProviderConstruction:

    def test_openai_client_constructed_with_given_base_url(self):
        _, _, mock_cls = _build_provider(
            OpenAICompatibleProvider,
            base_url="https://example.com/v1",
            api_key="k",
        )
        mock_cls.assert_called_once_with(
            base_url="https://example.com/v1",
            api_key="k",
        )

    def test_missing_api_key_falls_back_to_not_needed(self):
        _, _, mock_cls = _build_provider(
            OpenAICompatibleProvider,
            base_url="https://x.test/v1",
            api_key=None,
        )
        mock_cls.assert_called_once_with(
            base_url="https://x.test/v1",
            api_key="not-needed",
        )

    def test_explicit_api_key_passed_to_openai_client(self):
        _, _, mock_cls = _build_provider(
            OpenAICompatibleProvider,
            base_url="https://x.test/v1",
            api_key="secret-xyz",
        )
        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["api_key"] == "secret-xyz"

    def test_api_key_attribute_falls_back_to_not_needed_when_none(self):
        provider, _, _ = _build_provider(
            OpenAICompatibleProvider,
            base_url="https://x.test/v1",
            api_key=None,
        )
        assert provider.api_key == "not-needed"

    def test_api_key_attribute_stores_explicit_key(self):
        provider, _, _ = _build_provider(
            OpenAICompatibleProvider,
            base_url="https://x.test/v1",
            api_key="mine",
        )
        assert provider.api_key == "mine"

    def test_default_model_is_llama_3_3_70b_versatile(self):
        provider, _, _ = _build_provider(
            OpenAICompatibleProvider,
            base_url="https://x.test/v1",
            api_key="k",
        )
        assert provider._default_model == "llama-3.3-70b-versatile"

    def test_explicit_model_overrides_default(self):
        provider, _, _ = _build_provider(
            OpenAICompatibleProvider,
            base_url="https://x.test/v1",
            api_key="k",
            model="custom-model-7b",
        )
        assert provider._default_model == "custom-model-7b"

    def test_default_provider_name_is_openai_compatible(self):
        provider, _, _ = _build_provider(
            OpenAICompatibleProvider,
            base_url="https://x.test/v1",
            api_key="k",
        )
        assert provider.name == "openai-compatible"

    def test_explicit_provider_name_stored(self):
        provider, _, _ = _build_provider(
            OpenAICompatibleProvider,
            base_url="https://x.test/v1",
            api_key="k",
            provider_name="my-service",
        )
        assert provider.name == "my-service"

    def test_openai_provider_init_is_skipped(self):
        """
        The base class deliberately skips OpenAIProvider.__init__ to avoid
        falling back to OPENAI_API_KEY or overwriting the custom client.
        If OpenAIProvider.__init__ ran, api_key would pick up OPENAI_API_KEY
        instead of "not-needed".
        """
        provider, _, _ = _build_provider(
            OpenAICompatibleProvider,
            env={"OPENAI_API_KEY": "should-not-be-used"},
            base_url="https://x.test/v1",
            api_key=None,
        )
        assert provider.api_key == "not-needed"

    def test_provider_client_is_the_mocked_openai_client(self):
        provider, mock_client, _ = _build_provider(
            OpenAICompatibleProvider,
            base_url="https://x.test/v1",
            api_key="k",
        )
        assert provider.client is mock_client


class TestOpenAICompatibleProviderInheritedComplete:
    """
    OpenAICompatibleProvider inherits complete() from OpenAIProvider.
    Verify the inheritance actually works end-to-end with the custom client.
    """

    def _setup_provider(self):
        provider, mock_client, _ = _build_provider(
            OpenAICompatibleProvider,
            base_url="https://example.test/v1",
            api_key="k",
            model="foo-model",
        )
        return provider, mock_client

    def test_complete_returns_completion_response_with_parsed_content(self):
        provider, mock_client = self._setup_provider()
        mock_client.chat.completions.create.return_value = _make_chat_response(
            content="compat-says-hi",
            prompt_tokens=4,
            completion_tokens=6,
        )

        result = provider.complete([{"role": "user", "content": "Hi"}])

        assert isinstance(result, CompletionResponse)
        assert result.content == "compat-says-hi"
        assert result.usage["prompt_tokens"] == 4
        assert result.usage["completion_tokens"] == 6
        assert result.usage["total_tokens"] == 10
        assert result.tool_calls == []
        assert result.finish_reason == "stop"

    def test_complete_uses_the_configured_default_model(self):
        provider, mock_client = self._setup_provider()
        mock_client.chat.completions.create.return_value = _make_chat_response()

        provider.complete([{"role": "user", "content": "Hi"}])

        assert mock_client.chat.completions.create.call_args[1]["model"] == "foo-model"

    def test_complete_uses_explicit_model_over_default(self):
        provider, mock_client = self._setup_provider()
        mock_client.chat.completions.create.return_value = _make_chat_response()

        provider.complete(
            [{"role": "user", "content": "Hi"}],
            model="override-model",
        )

        assert mock_client.chat.completions.create.call_args[1]["model"] == "override-model"


# ===========================================================================
# GroqProvider
# ===========================================================================

class TestGroqProvider:

    def test_name_is_groq(self):
        provider, _, _ = _build_provider(GroqProvider, env={"GROQ_API_KEY": "k"})
        assert provider.name == "groq"

    def test_base_url_is_groq_openai_endpoint(self):
        _, _, mock_cls = _build_provider(GroqProvider, env={"GROQ_API_KEY": "k"})
        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["base_url"] == "https://api.groq.com/openai/v1"

    def test_api_key_read_from_groq_env_var(self):
        _, _, mock_cls = _build_provider(
            GroqProvider, env={"GROQ_API_KEY": "groq-env-key"},
        )
        assert mock_cls.call_args[1]["api_key"] == "groq-env-key"

    def test_explicit_api_key_overrides_env_var(self):
        _, _, mock_cls = _build_provider(
            GroqProvider,
            env={"GROQ_API_KEY": "env-key"},
            api_key="explicit-key",
        )
        assert mock_cls.call_args[1]["api_key"] == "explicit-key"

    def test_default_model_is_llama_3_1_8b_instant(self):
        provider, _, _ = _build_provider(GroqProvider, env={"GROQ_API_KEY": "k"})
        assert provider.default_model == "llama-3.1-8b-instant"

    def test_explicit_model_overrides_default(self):
        provider, _, _ = _build_provider(
            GroqProvider,
            env={"GROQ_API_KEY": "k"},
            model="mixtral-8x7b",
        )
        assert provider.default_model == "mixtral-8x7b"

    def test_missing_api_key_falls_back_to_not_needed(self):
        """No explicit key + no env var → OpenAI client gets 'not-needed'."""
        _, _, mock_cls = _build_provider(GroqProvider)
        assert mock_cls.call_args[1]["api_key"] == "not-needed"


# ===========================================================================
# OllamaProvider
# ===========================================================================

class TestOllamaProvider:

    def test_name_is_ollama(self):
        provider, _, _ = _build_provider(OllamaProvider)
        assert provider.name == "ollama"

    def test_default_base_url_is_localhost(self):
        _, _, mock_cls = _build_provider(OllamaProvider)
        assert mock_cls.call_args[1]["base_url"] == "http://localhost:11434/v1"

    def test_base_url_from_env_var(self):
        _, _, mock_cls = _build_provider(
            OllamaProvider,
            env={"OLLAMA_BASE_URL": "http://ollama.internal:9999/v1"},
        )
        assert mock_cls.call_args[1]["base_url"] == "http://ollama.internal:9999/v1"

    def test_explicit_base_url_overrides_env_var(self):
        _, _, mock_cls = _build_provider(
            OllamaProvider,
            env={"OLLAMA_BASE_URL": "http://env.host/v1"},
            base_url="http://explicit.host/v1",
        )
        assert mock_cls.call_args[1]["base_url"] == "http://explicit.host/v1"

    def test_default_model_is_llama3_1(self):
        provider, _, _ = _build_provider(OllamaProvider)
        assert provider.default_model == "llama3.1"

    def test_model_from_env_var(self):
        provider, _, _ = _build_provider(
            OllamaProvider,
            env={"OLLAMA_MODEL": "deepseek-v3"},
        )
        assert provider.default_model == "deepseek-v3"

    def test_explicit_model_overrides_env_var(self):
        provider, _, _ = _build_provider(
            OllamaProvider,
            env={"OLLAMA_MODEL": "env-model"},
            model="explicit-model",
        )
        assert provider.default_model == "explicit-model"

    def test_api_key_is_not_needed_regardless_of_environment(self):
        """Ollama explicitly passes api_key=None; it should never send a real key."""
        _, _, mock_cls = _build_provider(
            OllamaProvider,
            env={"OPENAI_API_KEY": "should-not-leak"},
        )
        assert mock_cls.call_args[1]["api_key"] == "not-needed"

    def test_api_key_attribute_is_not_needed(self):
        provider, _, _ = _build_provider(OllamaProvider)
        assert provider.api_key == "not-needed"


# ===========================================================================
# PerplexityProvider
# ===========================================================================

class TestPerplexityProviderConstruction:

    def test_name_is_perplexity(self):
        provider, _, _ = _build_provider(
            PerplexityProvider, env={"PERPLEXITY_API_KEY": "k"},
        )
        assert provider.name == "perplexity"

    def test_base_url_is_perplexity_api(self):
        _, _, mock_cls = _build_provider(
            PerplexityProvider, env={"PERPLEXITY_API_KEY": "k"},
        )
        assert mock_cls.call_args[1]["base_url"] == "https://api.perplexity.ai"

    def test_default_model_is_sonar_pro(self):
        provider, _, _ = _build_provider(
            PerplexityProvider, env={"PERPLEXITY_API_KEY": "k"},
        )
        assert provider.default_model == "sonar-pro"

    def test_explicit_model_overrides_default(self):
        provider, _, _ = _build_provider(
            PerplexityProvider,
            env={"PERPLEXITY_API_KEY": "k"},
            model="sonar",
        )
        assert provider.default_model == "sonar"

    def test_api_key_from_env_var(self):
        _, _, mock_cls = _build_provider(
            PerplexityProvider,
            env={"PERPLEXITY_API_KEY": "pplx-env"},
        )
        assert mock_cls.call_args[1]["api_key"] == "pplx-env"

    def test_explicit_api_key_overrides_env_var(self):
        _, _, mock_cls = _build_provider(
            PerplexityProvider,
            env={"PERPLEXITY_API_KEY": "env-key"},
            api_key="explicit-pplx",
        )
        assert mock_cls.call_args[1]["api_key"] == "explicit-pplx"


class TestPerplexityProviderComplete:
    """
    PerplexityProvider.complete() currently delegates to super().complete()
    unchanged (citation extraction is a TODO). These tests pin that behavior:
    if someone adds a broken transformation, they fail.
    """

    def _setup(self):
        provider, mock_client, _ = _build_provider(
            PerplexityProvider, env={"PERPLEXITY_API_KEY": "k"},
        )
        return provider, mock_client

    def test_complete_returns_parent_response_content(self):
        provider, mock_client = self._setup()
        mock_client.chat.completions.create.return_value = _make_chat_response(
            content="Perplexity answer with citations",
            prompt_tokens=12,
            completion_tokens=18,
        )

        result = provider.complete([{"role": "user", "content": "What is AB 1147?"}])

        assert result.content == "Perplexity answer with citations"
        assert result.usage["prompt_tokens"] == 12
        assert result.usage["completion_tokens"] == 18
        assert result.usage["total_tokens"] == 30

    def test_complete_passes_messages_unchanged_to_client(self):
        provider, mock_client = self._setup()
        mock_client.chat.completions.create.return_value = _make_chat_response()
        messages = [{"role": "user", "content": "What is AB 1147?"}]

        provider.complete(messages)

        sent = mock_client.chat.completions.create.call_args[1]["messages"]
        assert sent == [{"role": "user", "content": "What is AB 1147?"}]

    def test_complete_uses_default_model_when_unspecified(self):
        provider, mock_client = self._setup()
        mock_client.chat.completions.create.return_value = _make_chat_response()

        provider.complete([{"role": "user", "content": "Hi"}])

        assert mock_client.chat.completions.create.call_args[1]["model"] == "sonar-pro"

    def test_complete_respects_explicit_model(self):
        provider, mock_client = self._setup()
        mock_client.chat.completions.create.return_value = _make_chat_response()

        provider.complete([{"role": "user", "content": "Hi"}], model="sonar")

        assert mock_client.chat.completions.create.call_args[1]["model"] == "sonar"

    def test_complete_passes_temperature(self):
        provider, mock_client = self._setup()
        mock_client.chat.completions.create.return_value = _make_chat_response()

        provider.complete([{"role": "user", "content": "Hi"}], temperature=0.2)

        assert mock_client.chat.completions.create.call_args[1]["temperature"] == 0.2


# ===========================================================================
# OpenRouterProvider
# ===========================================================================

class TestOpenRouterProviderConstruction:

    def test_name_is_openrouter(self):
        provider, _, _ = _build_provider(
            OpenRouterProvider, env={"OPENROUTER_API_KEY": "k"},
        )
        assert provider.name == "openrouter"

    def test_base_url_is_openrouter_api(self):
        _, _, mock_cls = _build_provider(
            OpenRouterProvider, env={"OPENROUTER_API_KEY": "k"},
        )
        assert mock_cls.call_args[1]["base_url"] == "https://openrouter.ai/api/v1"

    def test_default_model_is_llama_3_3_70b_instruct(self):
        provider, _, _ = _build_provider(
            OpenRouterProvider, env={"OPENROUTER_API_KEY": "k"},
        )
        assert provider.default_model == "meta-llama/llama-3.3-70b-instruct"

    def test_explicit_model_overrides_default(self):
        provider, _, _ = _build_provider(
            OpenRouterProvider,
            env={"OPENROUTER_API_KEY": "k"},
            model="anthropic/claude-3.5-sonnet",
        )
        assert provider.default_model == "anthropic/claude-3.5-sonnet"

    def test_api_key_from_env_var(self):
        _, _, mock_cls = _build_provider(
            OpenRouterProvider, env={"OPENROUTER_API_KEY": "or-key"},
        )
        assert mock_cls.call_args[1]["api_key"] == "or-key"

    def test_explicit_api_key_overrides_env_var(self):
        _, _, mock_cls = _build_provider(
            OpenRouterProvider,
            env={"OPENROUTER_API_KEY": "env-key"},
            api_key="explicit",
        )
        assert mock_cls.call_args[1]["api_key"] == "explicit"

    def test_default_app_name_is_civic_conversational_os(self):
        provider, _, _ = _build_provider(
            OpenRouterProvider, env={"OPENROUTER_API_KEY": "k"},
        )
        assert provider.app_name == "civic-conversational-os"

    def test_default_site_url_is_civic_os_github(self):
        provider, _, _ = _build_provider(
            OpenRouterProvider, env={"OPENROUTER_API_KEY": "k"},
        )
        assert provider.site_url == "https://github.com/civic-os"

    def test_app_name_from_env_var(self):
        provider, _, _ = _build_provider(
            OpenRouterProvider,
            env={
                "OPENROUTER_API_KEY": "k",
                "OPENROUTER_APP_NAME": "my-custom-app",
            },
        )
        assert provider.app_name == "my-custom-app"

    def test_site_url_from_env_var(self):
        provider, _, _ = _build_provider(
            OpenRouterProvider,
            env={
                "OPENROUTER_API_KEY": "k",
                "OPENROUTER_SITE_URL": "https://my.site",
            },
        )
        assert provider.site_url == "https://my.site"


class TestOpenRouterProviderCompleteHeaders:
    """
    OpenRouterProvider.complete() injects HTTP-Referer and X-Title into
    extra_headers (for OpenRouter's usage-tracking and rankings), but must not
    clobber headers the caller already set.
    """

    def _setup(self, env=None):
        env = env or {"OPENROUTER_API_KEY": "k"}
        provider, mock_client, _ = _build_provider(OpenRouterProvider, env=env)
        mock_client.chat.completions.create.return_value = _make_chat_response()
        return provider, mock_client

    def test_injects_http_referer_header_from_site_url(self):
        provider, mock_client = self._setup()
        provider.complete([{"role": "user", "content": "Hi"}])
        sent_headers = mock_client.chat.completions.create.call_args[1]["extra_headers"]
        assert sent_headers["HTTP-Referer"] == "https://github.com/civic-os"

    def test_injects_x_title_header_from_app_name(self):
        provider, mock_client = self._setup()
        provider.complete([{"role": "user", "content": "Hi"}])
        sent_headers = mock_client.chat.completions.create.call_args[1]["extra_headers"]
        assert sent_headers["X-Title"] == "civic-conversational-os"

    def test_injects_env_overridden_site_url_as_http_referer(self):
        provider, mock_client = self._setup(env={
            "OPENROUTER_API_KEY": "k",
            "OPENROUTER_SITE_URL": "https://override.test",
        })
        provider.complete([{"role": "user", "content": "Hi"}])
        sent_headers = mock_client.chat.completions.create.call_args[1]["extra_headers"]
        assert sent_headers["HTTP-Referer"] == "https://override.test"

    def test_injects_env_overridden_app_name_as_x_title(self):
        provider, mock_client = self._setup(env={
            "OPENROUTER_API_KEY": "k",
            "OPENROUTER_APP_NAME": "my-app",
        })
        provider.complete([{"role": "user", "content": "Hi"}])
        sent_headers = mock_client.chat.completions.create.call_args[1]["extra_headers"]
        assert sent_headers["X-Title"] == "my-app"

    def test_does_not_overwrite_caller_http_referer(self):
        provider, mock_client = self._setup()
        provider.complete(
            [{"role": "user", "content": "Hi"}],
            extra_headers={"HTTP-Referer": "https://caller.com"},
        )
        sent_headers = mock_client.chat.completions.create.call_args[1]["extra_headers"]
        assert sent_headers["HTTP-Referer"] == "https://caller.com"
        # But X-Title still auto-injected
        assert sent_headers["X-Title"] == "civic-conversational-os"

    def test_does_not_overwrite_caller_x_title(self):
        provider, mock_client = self._setup()
        provider.complete(
            [{"role": "user", "content": "Hi"}],
            extra_headers={"X-Title": "My App"},
        )
        sent_headers = mock_client.chat.completions.create.call_args[1]["extra_headers"]
        assert sent_headers["X-Title"] == "My App"
        # HTTP-Referer still auto-injected
        assert sent_headers["HTTP-Referer"] == "https://github.com/civic-os"

    def test_preserves_caller_headers_alongside_injected_ones(self):
        provider, mock_client = self._setup()
        provider.complete(
            [{"role": "user", "content": "Hi"}],
            extra_headers={"X-Custom": "value-123"},
        )
        sent_headers = mock_client.chat.completions.create.call_args[1]["extra_headers"]
        assert sent_headers["X-Custom"] == "value-123"
        assert sent_headers["HTTP-Referer"] == "https://github.com/civic-os"
        assert sent_headers["X-Title"] == "civic-conversational-os"

    def test_empty_app_name_skips_both_header_injections(self):
        """
        The injection guard is `if self.app_name and ...`. Setting
        OPENROUTER_APP_NAME to an empty string makes self.app_name falsy, so
        neither HTTP-Referer nor X-Title is injected.
        """
        provider, mock_client = self._setup(env={
            "OPENROUTER_API_KEY": "k",
            "OPENROUTER_APP_NAME": "",
        })
        provider.complete([{"role": "user", "content": "Hi"}])
        sent_headers = mock_client.chat.completions.create.call_args[1]["extra_headers"]
        assert "HTTP-Referer" not in sent_headers
        assert "X-Title" not in sent_headers


class TestOpenRouterProviderCompleteDelegation:
    """complete() must still pass all other params through to the parent."""

    def _setup(self):
        provider, mock_client, _ = _build_provider(
            OpenRouterProvider, env={"OPENROUTER_API_KEY": "k"},
        )
        mock_client.chat.completions.create.return_value = _make_chat_response(
            content="router response",
            prompt_tokens=8,
            completion_tokens=12,
        )
        return provider, mock_client

    def test_returns_completion_response_from_parent(self):
        provider, _ = self._setup()
        result = provider.complete([{"role": "user", "content": "Hi"}])
        assert isinstance(result, CompletionResponse)
        assert result.content == "router response"
        assert result.usage["total_tokens"] == 20

    def test_passes_messages_through(self):
        provider, mock_client = self._setup()
        provider.complete([{"role": "user", "content": "Explain CDBG"}])
        sent = mock_client.chat.completions.create.call_args[1]["messages"]
        assert sent == [{"role": "user", "content": "Explain CDBG"}]

    def test_default_model_used_when_not_specified(self):
        provider, mock_client = self._setup()
        provider.complete([{"role": "user", "content": "Hi"}])
        sent_model = mock_client.chat.completions.create.call_args[1]["model"]
        assert sent_model == "meta-llama/llama-3.3-70b-instruct"

    def test_custom_model_passed_through(self):
        provider, mock_client = self._setup()
        provider.complete(
            [{"role": "user", "content": "Hi"}],
            model="anthropic/claude-3.5-sonnet",
        )
        sent_model = mock_client.chat.completions.create.call_args[1]["model"]
        assert sent_model == "anthropic/claude-3.5-sonnet"

    def test_temperature_passed_through(self):
        provider, mock_client = self._setup()
        provider.complete([{"role": "user", "content": "Hi"}], temperature=0.3)
        assert mock_client.chat.completions.create.call_args[1]["temperature"] == 0.3

    def test_max_tokens_passed_through(self):
        provider, mock_client = self._setup()
        provider.complete([{"role": "user", "content": "Hi"}], max_tokens=444)
        assert mock_client.chat.completions.create.call_args[1]["max_tokens"] == 444

    def test_tools_converted_and_passed_through(self):
        provider, mock_client = self._setup()
        tools = [{
            "name": "search_housing",
            "description": "Look up housing decisions",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
            },
        }]
        provider.complete([{"role": "user", "content": "Hi"}], tools=tools)

        sent_tools = mock_client.chat.completions.create.call_args[1]["tools"]
        assert len(sent_tools) == 1
        # OpenAIProvider wraps tools in {"type": "function", "function": {...}}
        assert sent_tools[0]["type"] == "function"
        assert sent_tools[0]["function"]["name"] == "search_housing"
        assert sent_tools[0]["function"]["description"] == "Look up housing decisions"
        assert sent_tools[0]["function"]["parameters"]["properties"]["query"]["type"] == "string"
