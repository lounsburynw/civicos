"""
Tests for llm_provider.py — provider factory routing, task-based model selection,
provider availability checks, and configuration validation.

Pure functions (is_provider_available, list_available_providers) tested with
controlled environment variables. Factory functions (get_provider, get_model,
get_model_for_task) tested with mocked provider classes (external I/O boundary).

To run:
    pytest packages/civicos-services/tests/test_llm_provider.py -q --override-ini="addopts="
"""

import os
from unittest.mock import patch, MagicMock

import pytest

from civicos_services.core.llm_provider import (
    TASK_MODEL_CONFIG,
    TASK_PROVIDER_CONFIG,
    get_model,
    get_model_for_task,
    get_provider,
    get_provider_for_task,
    get_provider_with_model,
    is_provider_available,
    list_available_providers,
)


# ---------------------------------------------------------------------------
# is_provider_available — env var logic
# ---------------------------------------------------------------------------

class TestIsProviderAvailable:
    def test_openai_available_when_key_set(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test123"}):
            assert is_provider_available("openai") is True

    def test_openai_unavailable_when_key_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            assert is_provider_available("openai") is False

    def test_openai_unavailable_when_key_empty(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=True):
            assert is_provider_available("openai") is False

    def test_google_available_when_key_set(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "AIza-test"}):
            assert is_provider_available("google") is True

    def test_google_unavailable_when_key_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            assert is_provider_available("google") is False

    def test_groq_available_when_key_set(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk-test"}):
            assert is_provider_available("groq") is True

    def test_groq_responses_shares_groq_key(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk-test"}):
            assert is_provider_available("groq-responses") is True

    def test_groq_responses_unavailable_without_groq_key(self):
        with patch.dict(os.environ, {}, clear=True):
            assert is_provider_available("groq-responses") is False

    def test_groq_unavailable_when_key_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            assert is_provider_available("groq") is False

    def test_anthropic_requires_flag_exactly_true(self):
        with patch.dict(os.environ, {"ENABLE_ANTHROPIC": "true"}):
            assert is_provider_available("anthropic") is True

    def test_anthropic_unavailable_when_flag_false(self):
        with patch.dict(os.environ, {"ENABLE_ANTHROPIC": "false"}):
            assert is_provider_available("anthropic") is False

    def test_anthropic_unavailable_when_flag_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            assert is_provider_available("anthropic") is False

    def test_anthropic_flag_case_insensitive(self):
        with patch.dict(os.environ, {"ENABLE_ANTHROPIC": "TRUE"}):
            assert is_provider_available("anthropic") is True

    def test_anthropic_rejects_non_true_values(self):
        with patch.dict(os.environ, {"ENABLE_ANTHROPIC": "yes"}):
            assert is_provider_available("anthropic") is False

    def test_ollama_always_available(self):
        with patch.dict(os.environ, {}, clear=True):
            assert is_provider_available("ollama") is True

    def test_perplexity_available_when_key_set(self):
        with patch.dict(os.environ, {"PERPLEXITY_API_KEY": "pplx-test"}):
            assert is_provider_available("perplexity") is True

    def test_perplexity_unavailable_when_key_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            assert is_provider_available("perplexity") is False

    def test_openrouter_available_when_key_set(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test"}):
            assert is_provider_available("openrouter") is True

    def test_openrouter_unavailable_when_key_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            assert is_provider_available("openrouter") is False

    def test_unknown_provider_returns_false(self):
        assert is_provider_available("nonexistent") is False

    def test_empty_string_returns_false(self):
        assert is_provider_available("") is False


# ---------------------------------------------------------------------------
# list_available_providers
# ---------------------------------------------------------------------------

class TestListAvailableProviders:
    def test_minimal_env_returns_openai_and_ollama_only(self):
        with patch.dict(os.environ, {}, clear=True):
            assert list_available_providers() == ["openai", "ollama"]

    def test_includes_google_when_key_set(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "AIza-test"}, clear=True):
            providers = list_available_providers()
            assert "google" in providers

    def test_excludes_google_when_key_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            assert "google" not in list_available_providers()

    def test_includes_groq_when_key_set(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk-test"}, clear=True):
            assert "groq" in list_available_providers()

    def test_includes_perplexity_when_key_set(self):
        with patch.dict(os.environ, {"PERPLEXITY_API_KEY": "pplx-test"}, clear=True):
            assert "perplexity" in list_available_providers()

    def test_includes_openrouter_when_key_set(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test"}, clear=True):
            assert "openrouter" in list_available_providers()

    def test_includes_anthropic_only_when_enabled(self):
        with patch.dict(os.environ, {"ENABLE_ANTHROPIC": "true"}, clear=True):
            assert "anthropic" in list_available_providers()

    def test_excludes_anthropic_when_not_enabled(self):
        with patch.dict(os.environ, {}, clear=True):
            assert "anthropic" not in list_available_providers()

    def test_all_providers_when_all_keys_set(self):
        env = {
            "OPENAI_API_KEY": "sk-test",
            "GOOGLE_API_KEY": "AIza-test",
            "GROQ_API_KEY": "gsk-test",
            "PERPLEXITY_API_KEY": "pplx-test",
            "OPENROUTER_API_KEY": "sk-or-test",
            "ENABLE_ANTHROPIC": "true",
        }
        with patch.dict(os.environ, env, clear=True):
            providers = list_available_providers()
            expected = {
                "openai", "google", "groq", "ollama",
                "perplexity", "openrouter", "anthropic",
            }
            assert set(providers) == expected


# ---------------------------------------------------------------------------
# get_provider — routing logic
# ---------------------------------------------------------------------------

class TestGetProvider:
    def test_defaults_to_openai_when_no_env(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("civicos_services.providers.openai_provider.OpenAIProvider") as MockCls:
                mock_inst = MagicMock()
                mock_inst.name = "openai"
                MockCls.return_value = mock_inst
                provider = get_provider()
                assert provider.name == "openai"

    def test_respects_llm_provider_env_var(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "google"}):
            with patch("civicos_services.providers.google_provider.GoogleProvider") as MockCls:
                mock_inst = MagicMock()
                mock_inst.name = "google"
                MockCls.return_value = mock_inst
                assert get_provider().name == "google"

    def test_explicit_name_overrides_env_var(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "openai"}):
            with patch("civicos_services.providers.google_provider.GoogleProvider") as MockCls:
                mock_inst = MagicMock()
                mock_inst.name = "google"
                MockCls.return_value = mock_inst
                assert get_provider("google").name == "google"

    def test_name_is_case_insensitive(self):
        with patch("civicos_services.providers.openai_compatible_provider.GroqProvider") as MockCls:
            mock_inst = MagicMock()
            mock_inst.name = "groq"
            MockCls.return_value = mock_inst
            assert get_provider("GROQ").name == "groq"

    def test_gemini_alias_routes_to_google(self):
        with patch("civicos_services.providers.google_provider.GoogleProvider") as MockCls:
            mock_inst = MagicMock()
            mock_inst.name = "google"
            MockCls.return_value = mock_inst
            assert get_provider("gemini").name == "google"

    def test_groq_responses_routes_correctly(self):
        with patch("civicos_services.providers.groq_responses_provider.GroqResponsesProvider") as MockCls:
            mock_inst = MagicMock()
            mock_inst.name = "groq-responses"
            MockCls.return_value = mock_inst
            assert get_provider("groq-responses").name == "groq-responses"

    def test_ollama_routes_correctly(self):
        with patch("civicos_services.providers.openai_compatible_provider.OllamaProvider") as MockCls:
            mock_inst = MagicMock()
            mock_inst.name = "ollama"
            MockCls.return_value = mock_inst
            assert get_provider("ollama").name == "ollama"

    def test_perplexity_routes_correctly(self):
        with patch("civicos_services.providers.openai_compatible_provider.PerplexityProvider") as MockCls:
            mock_inst = MagicMock()
            mock_inst.name = "perplexity"
            MockCls.return_value = mock_inst
            assert get_provider("perplexity").name == "perplexity"

    def test_openrouter_routes_correctly(self):
        with patch("civicos_services.providers.openai_compatible_provider.OpenRouterProvider") as MockCls:
            mock_inst = MagicMock()
            mock_inst.name = "openrouter"
            MockCls.return_value = mock_inst
            assert get_provider("openrouter").name == "openrouter"

    def test_anthropic_raises_when_not_enabled(self):
        with patch.dict(os.environ, {"ENABLE_ANTHROPIC": "false"}):
            with pytest.raises(ValueError, match="Anthropic provider not enabled"):
                get_provider("anthropic")

    def test_anthropic_raises_when_flag_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Set ENABLE_ANTHROPIC=true"):
                get_provider("anthropic")

    def test_unknown_provider_raises_with_name(self):
        with pytest.raises(ValueError, match="Unknown provider: foobar"):
            get_provider("foobar")

    def test_error_lists_supported_providers(self):
        with pytest.raises(ValueError, match="Supported:.*openai.*google.*groq"):
            get_provider("nonexistent")


# ---------------------------------------------------------------------------
# get_provider_with_model — model override routing
# ---------------------------------------------------------------------------

class TestGetProviderWithModel:
    def test_openai_sets_private_model_attr(self):
        with patch("civicos_services.providers.openai_provider.OpenAIProvider") as MockCls:
            mock_inst = MagicMock()
            MockCls.return_value = mock_inst
            provider = get_provider_with_model("openai", "gpt-4o")
            assert provider._default_model == "gpt-4o"

    def test_google_passes_model_to_constructor(self):
        with patch("civicos_services.providers.google_provider.GoogleProvider") as MockCls:
            mock_inst = MagicMock()
            mock_inst.name = "google"
            MockCls.return_value = mock_inst
            provider = get_provider_with_model("google", "gemini-1.5-pro-latest")
            assert provider is mock_inst
            MockCls.assert_called_once_with(model="gemini-1.5-pro-latest")

    def test_gemini_alias_routes_to_google_constructor(self):
        with patch("civicos_services.providers.google_provider.GoogleProvider") as MockCls:
            mock_inst = MagicMock()
            MockCls.return_value = mock_inst
            provider = get_provider_with_model("gemini", "gemini-2.5-pro")
            assert provider is mock_inst
            MockCls.assert_called_once_with(model="gemini-2.5-pro")

    def test_groq_passes_model_to_constructor(self):
        with patch("civicos_services.providers.openai_compatible_provider.GroqProvider") as MockCls:
            mock_inst = MagicMock()
            MockCls.return_value = mock_inst
            provider = get_provider_with_model("groq", "llama-3.1-8b-instant")
            assert provider is mock_inst
            MockCls.assert_called_once_with(model="llama-3.1-8b-instant")

    def test_groq_responses_sets_default_model_attr(self):
        with patch("civicos_services.providers.groq_responses_provider.GroqResponsesProvider") as MockCls:
            mock_inst = MagicMock()
            MockCls.return_value = mock_inst
            provider = get_provider_with_model("groq-responses", "llama-3.3-70b-versatile")
            assert provider.default_model == "llama-3.3-70b-versatile"

    def test_ollama_passes_model_to_constructor(self):
        with patch("civicos_services.providers.openai_compatible_provider.OllamaProvider") as MockCls:
            mock_inst = MagicMock()
            MockCls.return_value = mock_inst
            provider = get_provider_with_model("ollama", "mistral")
            assert provider is mock_inst
            MockCls.assert_called_once_with(model="mistral")

    def test_perplexity_passes_model_to_constructor(self):
        with patch("civicos_services.providers.openai_compatible_provider.PerplexityProvider") as MockCls:
            mock_inst = MagicMock()
            MockCls.return_value = mock_inst
            provider = get_provider_with_model("perplexity", "sonar-pro")
            assert provider is mock_inst
            MockCls.assert_called_once_with(model="sonar-pro")

    def test_openrouter_passes_model_to_constructor(self):
        with patch("civicos_services.providers.openai_compatible_provider.OpenRouterProvider") as MockCls:
            mock_inst = MagicMock()
            MockCls.return_value = mock_inst
            provider = get_provider_with_model("openrouter", "deepseek/deepseek-chat")
            assert provider is mock_inst
            MockCls.assert_called_once_with(model="deepseek/deepseek-chat")

    def test_unhandled_provider_delegates_to_get_provider(self):
        """Providers not in the if/elif chain fall through to get_provider."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Anthropic provider not enabled"):
                get_provider_with_model("anthropic", "claude-sonnet-4")


# ---------------------------------------------------------------------------
# get_model — model-first factory
# ---------------------------------------------------------------------------

class TestGetModel:
    def test_unknown_model_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown model: nonexistent"):
            get_model("nonexistent")

    def test_error_mentions_model_registry(self):
        with pytest.raises(ValueError, match="MODEL_REGISTRY"):
            get_model("fake-model-xyz")

    def test_openai_model_sets_correct_model(self):
        with patch("civicos_services.providers.openai_provider.OpenAIProvider") as MockCls:
            mock_inst = MagicMock()
            MockCls.return_value = mock_inst
            provider = get_model("gpt-4o-mini")
            assert provider._default_model == "gpt-4o-mini"

    def test_google_model_passes_to_constructor(self):
        with patch("civicos_services.providers.google_provider.GoogleProvider") as MockCls:
            mock_inst = MagicMock()
            MockCls.return_value = mock_inst
            provider = get_model("gemini-1.5-pro-latest")
            assert provider is mock_inst
            MockCls.assert_called_once_with(model="gemini-1.5-pro-latest")

    def test_alias_resolves_to_canonical_name(self):
        """gemini-2.0-flash-exp resolves to models/gemini-2.0-flash."""
        with patch("civicos_services.providers.google_provider.GoogleProvider") as MockCls:
            mock_inst = MagicMock()
            MockCls.return_value = mock_inst
            provider = get_model("gemini-2.0-flash-exp")
            assert provider is mock_inst
            MockCls.assert_called_once_with(model="models/gemini-2.0-flash")

    def test_groq_model_routes_correctly(self):
        with patch("civicos_services.providers.openai_compatible_provider.GroqProvider") as MockCls:
            mock_inst = MagicMock()
            MockCls.return_value = mock_inst
            provider = get_model("llama-3.1-8b-instant")
            assert provider is mock_inst
            MockCls.assert_called_once_with(model="llama-3.1-8b-instant")

    def test_openrouter_model_routes_correctly(self):
        with patch("civicos_services.providers.openai_compatible_provider.OpenRouterProvider") as MockCls:
            mock_inst = MagicMock()
            MockCls.return_value = mock_inst
            provider = get_model("deepseek/deepseek-chat")
            assert provider is mock_inst
            MockCls.assert_called_once_with(model="deepseek/deepseek-chat")

    def test_perplexity_model_routes_correctly(self):
        with patch("civicos_services.providers.openai_compatible_provider.PerplexityProvider") as MockCls:
            mock_inst = MagicMock()
            MockCls.return_value = mock_inst
            provider = get_model("sonar")
            assert provider is mock_inst
            MockCls.assert_called_once_with(model="sonar")


# ---------------------------------------------------------------------------
# get_provider_for_task — legacy task routing
# ---------------------------------------------------------------------------

class TestGetProviderForTask:
    def test_unknown_task_defaults_to_openai(self):
        with patch("civicos_services.providers.openai_provider.OpenAIProvider") as MockCls:
            mock_inst = MagicMock()
            mock_inst.name = "openai"
            MockCls.return_value = mock_inst
            assert get_provider_for_task("nonexistent_task").name == "openai"

    def test_uses_first_available_provider(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            with patch("civicos_services.providers.openai_provider.OpenAIProvider") as MockCls:
                mock_inst = MagicMock()
                mock_inst.name = "openai"
                MockCls.return_value = mock_inst
                assert get_provider_for_task("navigation").name == "openai"

    def test_skips_unavailable_provider_to_next(self):
        # research priority: ['google', 'anthropic', 'openai']
        # Only openai key set → google/anthropic skipped
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            with patch("civicos_services.providers.openai_provider.OpenAIProvider") as MockCls:
                mock_inst = MagicMock()
                mock_inst.name = "openai"
                MockCls.return_value = mock_inst
                assert get_provider_for_task("research").name == "openai"

    def test_provider_model_notation_passes_model(self):
        """long_document uses 'google:gemini-1.5-pro-latest' notation."""
        assert TASK_PROVIDER_CONFIG["long_document"]["priority"][0] == "google:gemini-1.5-pro-latest"
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "AIza-test"}, clear=True):
            with patch("civicos_services.providers.google_provider.GoogleProvider") as MockCls:
                mock_inst = MagicMock()
                mock_inst.name = "google"
                MockCls.return_value = mock_inst
                get_provider_for_task("long_document")
                MockCls.assert_called_once_with(model="gemini-1.5-pro-latest")

    def test_uses_fallback_when_all_unavailable(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("civicos_services.providers.openai_provider.OpenAIProvider") as MockCls:
                mock_inst = MagicMock()
                mock_inst.name = "openai"
                MockCls.return_value = mock_inst
                # realtime_research: priority [perplexity, google, openai] all need keys
                # fallback is 'openai' → get_provider('openai')
                assert get_provider_for_task("realtime_research").name == "openai"


# ---------------------------------------------------------------------------
# get_model_for_task — model-first task routing
# ---------------------------------------------------------------------------

class TestGetModelForTask:
    def test_unknown_task_defaults_to_gpt4o_mini(self):
        with patch("civicos_services.providers.openai_provider.OpenAIProvider") as MockCls:
            mock_inst = MagicMock()
            MockCls.return_value = mock_inst
            provider = get_model_for_task("nonexistent_task")
            assert provider._default_model == "gpt-4o-mini"

    def test_legacy_mode_delegates_to_provider_for_task(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            with patch("civicos_services.providers.openai_provider.OpenAIProvider") as MockCls:
                mock_inst = MagicMock()
                mock_inst.name = "openai"
                MockCls.return_value = mock_inst
                provider = get_model_for_task("navigation", use_model_config=False)
                assert provider.name == "openai"

    def test_explicit_strategy_selects_first_available_model(self):
        # navigation first model is gemini-2.0-flash-exp (google provider)
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "AIza-test"}, clear=True):
            with patch("civicos_services.providers.google_provider.GoogleProvider") as MockCls:
                mock_inst = MagicMock()
                MockCls.return_value = mock_inst
                provider = get_model_for_task("navigation")
                assert provider is mock_inst
                # Alias resolved: gemini-2.0-flash-exp → models/gemini-2.0-flash
                MockCls.assert_called_once_with(model="models/gemini-2.0-flash")

    def test_cost_optimized_picks_cheapest_available(self):
        # research: cost_optimized, max_cost=0.10, requires structured_outputs
        # With only groq key, cheapest is llama-3.1-8b-instant ($0.05)
        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk-test"}, clear=True):
            with patch("civicos_services.providers.openai_compatible_provider.GroqProvider") as MockCls:
                mock_inst = MagicMock()
                MockCls.return_value = mock_inst
                provider = get_model_for_task("research")
                assert provider is mock_inst
                MockCls.assert_called_once_with(model="llama-3.1-8b-instant")

    def test_falls_back_when_no_models_available(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("civicos_services.providers.openai_provider.OpenAIProvider") as MockCls:
                mock_inst = MagicMock()
                MockCls.return_value = mock_inst
                provider = get_model_for_task("navigation")
                assert provider._default_model == "gpt-4o-mini"

    def test_import_error_skips_to_next_model(self):
        """If provider SDK not installed, gracefully skips to next model."""
        with patch.dict(
            os.environ,
            {"GOOGLE_API_KEY": "AIza-test", "OPENAI_API_KEY": "sk-test"},
            clear=True,
        ):
            with patch(
                "civicos_services.providers.google_provider.GoogleProvider",
                side_effect=ImportError("no google SDK"),
            ):
                with patch("civicos_services.providers.openai_provider.OpenAIProvider") as MockOAI:
                    mock_inst = MagicMock()
                    MockOAI.return_value = mock_inst
                    provider = get_model_for_task("navigation")
                    # Gemini raised ImportError, should fall to an OpenAI model
                    assert provider._default_model == "gpt-4o-mini"


# ---------------------------------------------------------------------------
# TASK_PROVIDER_CONFIG structure validation
# ---------------------------------------------------------------------------

class TestTaskProviderConfig:
    def test_all_entries_have_required_keys(self):
        for task, config in TASK_PROVIDER_CONFIG.items():
            assert "priority" in config, f"{task} missing 'priority'"
            assert "reason" in config, f"{task} missing 'reason'"
            assert "fallback_model" in config, f"{task} missing 'fallback_model'"

    def test_priority_lists_are_non_empty(self):
        for task, config in TASK_PROVIDER_CONFIG.items():
            assert len(config["priority"]) >= 1, f"{task} has empty priority"

    def test_expected_task_types_present(self):
        expected = {"navigation", "explain", "research", "long_document",
                    "draft", "conversational", "realtime_research"}
        assert expected.issubset(set(TASK_PROVIDER_CONFIG.keys()))

    def test_navigation_first_priority_is_openai(self):
        assert TASK_PROVIDER_CONFIG["navigation"]["priority"][0] == "openai"

    def test_realtime_research_first_priority_is_perplexity(self):
        assert TASK_PROVIDER_CONFIG["realtime_research"]["priority"][0] == "perplexity"

    def test_fallback_models_are_known_providers(self):
        valid = {"openai", "google", "groq", "ollama", "perplexity", "openrouter", "anthropic"}
        for task, config in TASK_PROVIDER_CONFIG.items():
            assert config["fallback_model"] in valid, \
                f"{task} fallback '{config['fallback_model']}' not a known provider"


# ---------------------------------------------------------------------------
# TASK_MODEL_CONFIG structure validation
# ---------------------------------------------------------------------------

class TestTaskModelConfig:
    def test_all_entries_have_required_keys(self):
        for task, config in TASK_MODEL_CONFIG.items():
            assert "strategy" in config, f"{task} missing 'strategy'"
            assert "reason" in config, f"{task} missing 'reason'"
            assert "fallback_model" in config, f"{task} missing 'fallback_model'"
            assert "required_capabilities" in config, f"{task} missing 'required_capabilities'"

    def test_strategies_are_valid(self):
        for task, config in TASK_MODEL_CONFIG.items():
            assert config["strategy"] in {"explicit", "cost_optimized"}, \
                f"{task} has invalid strategy '{config['strategy']}'"

    def test_explicit_strategies_have_model_priority(self):
        for task, config in TASK_MODEL_CONFIG.items():
            if config["strategy"] == "explicit":
                assert "model_priority" in config, f"{task} explicit but no model_priority"
                assert len(config["model_priority"]) >= 1, f"{task} has empty model_priority"

    def test_cost_optimized_strategies_have_max_cost(self):
        for task, config in TASK_MODEL_CONFIG.items():
            if config["strategy"] == "cost_optimized":
                assert "max_cost_per_1m" in config, f"{task} cost_optimized but no max_cost"

    def test_expected_task_types_present(self):
        expected = {
            "navigation", "explain", "research", "long_document", "draft",
            "conversational", "query_planning", "realtime_research",
            "agenda_parsing", "legislative_validation", "personalization",
        }
        assert expected.issubset(set(TASK_MODEL_CONFIG.keys()))

    def test_navigation_first_model_is_gemini_flash(self):
        assert TASK_MODEL_CONFIG["navigation"]["model_priority"][0] == "gemini-2.0-flash-exp"

    def test_research_max_cost_is_ten_cents(self):
        assert TASK_MODEL_CONFIG["research"]["max_cost_per_1m"] == 0.10

    def test_long_document_requires_long_context(self):
        caps = TASK_MODEL_CONFIG["long_document"]["required_capabilities"]
        assert "long_context" in caps

    def test_long_document_min_context_is_500k(self):
        assert TASK_MODEL_CONFIG["long_document"]["min_context_window"] >= 500000

    def test_realtime_research_requires_web_search_and_citations(self):
        caps = TASK_MODEL_CONFIG["realtime_research"]["required_capabilities"]
        assert "web_search" in caps
        assert "citations" in caps

    def test_personalization_uses_cost_optimized(self):
        assert TASK_MODEL_CONFIG["personalization"]["strategy"] == "cost_optimized"
        assert TASK_MODEL_CONFIG["personalization"]["max_cost_per_1m"] == 0.10
