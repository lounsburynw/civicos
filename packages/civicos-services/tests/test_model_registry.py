"""
Tests for model_registry.py — model metadata lookup, alias resolution,
capability-based filtering, provider availability, cost calculation.

Pure functions (get_model_info, resolve_model_name, find_models_by_capabilities,
get_models_by_provider, calculate_cost) tested with real MODEL_REGISTRY data.
Environment-dependent functions (is_model_available, get_available_models,
get_cheapest_model) tested with controlled env vars.

To run:
    pytest packages/civicos-services/tests/test_model_registry.py -q --override-ini="addopts="
"""

import os
from unittest.mock import patch

import pytest

from civicos_services.core.model_registry import (
    MODEL_REGISTRY,
    calculate_cost,
    find_models_by_capabilities,
    get_available_models,
    get_cheapest_model,
    get_model_info,
    get_models_by_provider,
    is_model_available,
    resolve_model_name,
)


# ---------------------------------------------------------------------------
# get_model_info — metadata lookup with alias resolution
# ---------------------------------------------------------------------------


class TestGetModelInfo:
    def test_returns_metadata_for_known_model(self):
        info = get_model_info("gpt-4o-mini")
        assert info["provider"] == "openai"
        assert info["cost_per_1m_tokens"] == 0.60
        assert info["context_window"] == 128000
        assert "structured_outputs" in info["capabilities"]

    def test_returns_none_for_unknown_model(self):
        assert get_model_info("nonexistent-model-xyz") is None

    def test_resolves_alias_to_canonical_model(self):
        # gemini-2.0-flash-exp is an alias for models/gemini-2.0-flash
        info = get_model_info("gemini-2.0-flash-exp")
        canonical_info = get_model_info("models/gemini-2.0-flash")
        assert info == canonical_info
        assert info["provider"] == "google"
        assert "alias_for" not in info  # resolved, not the alias entry

    def test_returns_direct_entry_for_non_alias(self):
        info = get_model_info("claude-sonnet-4")
        assert info["provider"] == "anthropic"
        assert "alias_for" not in info

    def test_returns_correct_capabilities_for_multimodal_model(self):
        info = get_model_info("gpt-4o")
        assert "vision" in info["capabilities"]
        assert "structured_outputs" in info["capabilities"]

    def test_returns_correct_speed_tier(self):
        assert get_model_info("llama-3.1-8b-instant")["speed"] == "ultra_fast"
        assert get_model_info("gpt-4o-mini")["speed"] == "fast"
        assert get_model_info("claude-sonnet-4")["speed"] == "medium"

    def test_openrouter_model_returns_openrouter_provider(self):
        info = get_model_info("anthropic/claude-3.5-sonnet")
        assert info["provider"] == "openrouter"

    def test_perplexity_model_has_web_search_capability(self):
        info = get_model_info("sonar-pro")
        assert "web_search" in info["capabilities"]
        assert "citations" in info["capabilities"]


# ---------------------------------------------------------------------------
# resolve_model_name — alias to canonical name mapping
# ---------------------------------------------------------------------------


class TestResolveModelName:
    def test_resolves_alias_to_canonical_name(self):
        assert resolve_model_name("gemini-2.0-flash-exp") == "models/gemini-2.0-flash"

    def test_returns_same_name_for_non_alias(self):
        assert resolve_model_name("gpt-4o-mini") == "gpt-4o-mini"

    def test_returns_same_name_for_unknown_model(self):
        assert resolve_model_name("nonexistent-model") == "nonexistent-model"

    def test_canonical_name_resolves_to_itself(self):
        assert resolve_model_name("models/gemini-2.0-flash") == "models/gemini-2.0-flash"


# ---------------------------------------------------------------------------
# find_models_by_capabilities — filtering and sorting
# ---------------------------------------------------------------------------


class TestFindModelsByCapabilities:
    def test_finds_models_with_structured_outputs(self):
        models = find_models_by_capabilities(["structured_outputs"])
        assert len(models) >= 5  # many models have this
        # All returned models must have the capability
        for m in models:
            assert "structured_outputs" in MODEL_REGISTRY[m]["capabilities"]

    def test_results_sorted_by_cost_ascending(self):
        models = find_models_by_capabilities(["structured_outputs"])
        costs = [MODEL_REGISTRY[m]["cost_per_1m_tokens"] for m in models]
        assert costs == sorted(costs)

    def test_filters_by_max_cost(self):
        models = find_models_by_capabilities(["structured_outputs"], max_cost=0.10)
        for m in models:
            assert MODEL_REGISTRY[m]["cost_per_1m_tokens"] <= 0.10
        # Should include cheap models
        assert "llama-3.1-8b-instant" in models
        # Should exclude expensive models
        assert "gpt-4o" not in models

    def test_filters_by_min_context(self):
        models = find_models_by_capabilities(
            ["structured_outputs"], min_context=500000
        )
        for m in models:
            assert MODEL_REGISTRY[m]["context_window"] >= 500000

    def test_filters_by_speed_tier(self):
        # very_fast should include very_fast and ultra_fast models
        models = find_models_by_capabilities(
            ["structured_outputs"], speed="very_fast"
        )
        for m in models:
            assert MODEL_REGISTRY[m]["speed"] in ("very_fast", "ultra_fast")

    def test_ultra_fast_speed_excludes_fast_and_medium(self):
        models = find_models_by_capabilities(
            ["structured_outputs"], speed="ultra_fast"
        )
        for m in models:
            assert MODEL_REGISTRY[m]["speed"] == "ultra_fast"

    def test_multiple_required_capabilities_narrows_results(self):
        broad = find_models_by_capabilities(["structured_outputs"])
        narrow = find_models_by_capabilities(["structured_outputs", "vision"])
        assert len(narrow) < len(broad)
        for m in narrow:
            caps = MODEL_REGISTRY[m]["capabilities"]
            assert "structured_outputs" in caps
            assert "vision" in caps

    def test_impossible_capability_returns_empty(self):
        models = find_models_by_capabilities(["teleportation"])
        assert models == []

    def test_empty_required_returns_all_models(self):
        models = find_models_by_capabilities([])
        assert len(models) == len(MODEL_REGISTRY)

    def test_combined_filters_narrow_progressively(self):
        all_structured = find_models_by_capabilities(["structured_outputs"])
        cheap_structured = find_models_by_capabilities(
            ["structured_outputs"], max_cost=1.0
        )
        cheap_fast_structured = find_models_by_capabilities(
            ["structured_outputs"], max_cost=1.0, speed="fast"
        )
        assert len(cheap_structured) <= len(all_structured)
        assert len(cheap_fast_structured) <= len(cheap_structured)

    def test_max_cost_zero_only_returns_free_models(self):
        models = find_models_by_capabilities([], max_cost=0.0)
        for m in models:
            assert MODEL_REGISTRY[m]["cost_per_1m_tokens"] == 0.0

    def test_long_context_capability_filter(self):
        models = find_models_by_capabilities(["long_context"])
        for m in models:
            assert "long_context" in MODEL_REGISTRY[m]["capabilities"]
        # Gemini pro models have long_context
        assert "gemini-1.5-pro-latest" in models


# ---------------------------------------------------------------------------
# is_model_available — env-based provider checks
# ---------------------------------------------------------------------------


class TestIsModelAvailable:
    def test_openai_model_available_when_key_set(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            assert is_model_available("gpt-4o-mini") is True

    def test_openai_model_unavailable_when_key_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            assert is_model_available("gpt-4o-mini") is False

    def test_google_model_available_when_key_set(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "AIza-test"}, clear=True):
            assert is_model_available("models/gemini-2.0-flash") is True

    def test_google_model_unavailable_when_key_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            assert is_model_available("models/gemini-2.0-flash") is False

    def test_anthropic_model_available_when_key_set(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=True):
            assert is_model_available("claude-sonnet-4") is True

    def test_anthropic_model_unavailable_when_key_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            assert is_model_available("claude-sonnet-4") is False

    def test_groq_model_available_when_key_set(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk-test"}, clear=True):
            assert is_model_available("llama-3.1-8b-instant") is True

    def test_groq_model_unavailable_when_key_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            assert is_model_available("llama-3.1-8b-instant") is False

    def test_perplexity_model_available_when_key_set(self):
        with patch.dict(os.environ, {"PERPLEXITY_API_KEY": "pplx-test"}, clear=True):
            assert is_model_available("sonar-pro") is True

    def test_perplexity_model_unavailable_when_key_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            assert is_model_available("sonar-pro") is False

    def test_openrouter_model_available_when_key_set(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test"}, clear=True):
            assert is_model_available("anthropic/claude-3.5-sonnet") is True

    def test_openrouter_model_unavailable_when_key_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            assert is_model_available("anthropic/claude-3.5-sonnet") is False

    def test_unknown_model_is_unavailable(self):
        assert is_model_available("nonexistent-model-xyz") is False

    def test_alias_model_checks_canonical_provider(self):
        # gemini-2.0-flash-exp aliases to models/gemini-2.0-flash (google)
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "AIza-test"}, clear=True):
            assert is_model_available("gemini-2.0-flash-exp") is True

    def test_empty_api_key_treated_as_unavailable(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=True):
            assert is_model_available("gpt-4o-mini") is False


# ---------------------------------------------------------------------------
# get_available_models — bulk availability
# ---------------------------------------------------------------------------


class TestGetAvailableModels:
    def test_returns_only_configured_models(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            available = get_available_models()
        # Should include OpenAI models
        assert "gpt-4o-mini" in available
        assert "gpt-4o" in available
        # Should exclude non-OpenAI models
        assert "claude-sonnet-4" not in available
        assert "llama-3.1-8b-instant" not in available

    def test_returns_empty_when_no_keys_set(self):
        with patch.dict(os.environ, {}, clear=True):
            available = get_available_models()
        assert available == []

    def test_multiple_providers_configured(self):
        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "sk-test", "GROQ_API_KEY": "gsk-test"},
            clear=True,
        ):
            available = get_available_models()
        assert "gpt-4o-mini" in available
        assert "llama-3.1-8b-instant" in available
        assert "claude-sonnet-4" not in available


# ---------------------------------------------------------------------------
# get_cheapest_model — availability-aware cost optimization
# ---------------------------------------------------------------------------


class TestGetCheapestModel:
    def test_returns_cheapest_available_model(self):
        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "sk-test", "GROQ_API_KEY": "gsk-test"},
            clear=True,
        ):
            cheapest = get_cheapest_model(["structured_outputs"])
        # Groq llama-3.1-8b-instant at $0.05 is cheaper than gpt-4o-mini at $0.60
        assert cheapest == "llama-3.1-8b-instant"

    def test_returns_none_when_no_models_available(self):
        with patch.dict(os.environ, {}, clear=True):
            assert get_cheapest_model(["structured_outputs"]) is None

    def test_returns_none_when_no_models_match_capabilities(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            assert get_cheapest_model(["teleportation"]) is None

    def test_respects_max_cost_constraint(self):
        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "sk-test", "GROQ_API_KEY": "gsk-test"},
            clear=True,
        ):
            # max_cost=0.04 excludes llama-3.1-8b-instant ($0.05)
            result = get_cheapest_model(["structured_outputs"], max_cost=0.04)
        assert result is None

    def test_skips_unavailable_cheaper_model(self):
        # Only OpenAI configured, not Groq — so Groq's cheaper models excluded
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            cheapest = get_cheapest_model(["structured_outputs"])
        assert cheapest == "gpt-4o-mini"


# ---------------------------------------------------------------------------
# get_models_by_provider — provider grouping
# ---------------------------------------------------------------------------


class TestGetModelsByProvider:
    def test_openai_provider_returns_openai_models(self):
        models = get_models_by_provider("openai")
        assert "gpt-4o-mini" in models
        assert "gpt-4o" in models
        # Non-OpenAI models excluded
        assert "claude-sonnet-4" not in models

    def test_google_provider_returns_google_models(self):
        models = get_models_by_provider("google")
        assert "models/gemini-2.0-flash" in models
        assert "gemini-2.5-pro" in models
        # Alias entry also returned (it has provider=google)
        assert "gemini-2.0-flash-exp" in models

    def test_groq_provider_returns_groq_models(self):
        models = get_models_by_provider("groq")
        assert "llama-3.1-8b-instant" in models
        assert "llama-3.3-70b-versatile" in models

    def test_openrouter_provider_returns_openrouter_models(self):
        models = get_models_by_provider("openrouter")
        assert "anthropic/claude-3.5-sonnet" in models
        assert "deepseek/deepseek-r1" in models
        # Direct provider models excluded
        assert "gpt-4o-mini" not in models

    def test_unknown_provider_returns_empty(self):
        assert get_models_by_provider("nonexistent-provider") == []

    def test_each_returned_model_belongs_to_requested_provider(self):
        for provider in ["openai", "google", "anthropic", "groq", "perplexity", "openrouter"]:
            models = get_models_by_provider(provider)
            for m in models:
                assert MODEL_REGISTRY[m]["provider"] == provider


# ---------------------------------------------------------------------------
# calculate_cost — token-based cost math
# ---------------------------------------------------------------------------


class TestCalculateCost:
    def test_cost_from_total_tokens(self):
        # gpt-4o-mini: $0.60/1M tokens; 10,000 tokens = $0.006
        cost = calculate_cost("gpt-4o-mini", {"total_tokens": 10_000})
        assert cost == pytest.approx(0.006, abs=1e-8)

    def test_cost_from_prompt_plus_completion_tokens(self):
        # gpt-4o-mini: 600 + 400 = 1000 tokens = $0.0006
        cost = calculate_cost(
            "gpt-4o-mini",
            {"prompt_tokens": 600, "completion_tokens": 400},
        )
        assert cost == pytest.approx(0.0006, abs=1e-8)

    def test_total_tokens_takes_precedence_over_components(self):
        # When both total and components present, total wins
        cost = calculate_cost(
            "gpt-4o-mini",
            {"prompt_tokens": 999, "completion_tokens": 999, "total_tokens": 1000},
        )
        # Should use total_tokens=1000, not 999+999=1998
        assert cost == pytest.approx(0.0006, abs=1e-8)

    def test_empty_usage_returns_zero(self):
        assert calculate_cost("gpt-4o-mini", {}) == 0.0

    def test_none_usage_returns_zero(self):
        assert calculate_cost("gpt-4o-mini", None) == 0.0

    def test_unknown_model_returns_zero(self):
        assert calculate_cost("nonexistent-model", {"total_tokens": 10_000}) == 0.0

    def test_zero_tokens_returns_zero(self):
        assert calculate_cost("gpt-4o-mini", {"total_tokens": 0}) == 0.0

    def test_free_model_returns_zero(self):
        # google/gemini-2.0-flash-exp:free has cost_per_1m_tokens = 0.0
        cost = calculate_cost(
            "google/gemini-2.0-flash-exp:free", {"total_tokens": 1_000_000}
        )
        assert cost == 0.0

    def test_alias_model_uses_canonical_pricing(self):
        # gemini-2.0-flash-exp aliases to models/gemini-2.0-flash ($0.075/1M)
        cost = calculate_cost(
            "gemini-2.0-flash-exp", {"total_tokens": 1_000_000}
        )
        assert cost == pytest.approx(0.075, abs=1e-8)

    def test_expensive_model_high_token_count(self):
        # gpt-4o: $5.00/1M tokens; 1M tokens = $5.00
        cost = calculate_cost("gpt-4o", {"total_tokens": 1_000_000})
        assert cost == pytest.approx(5.0, abs=1e-6)

    def test_groq_cheapest_model_cost(self):
        # llama-3.1-8b-instant: $0.05/1M; 100K tokens = $0.005
        cost = calculate_cost(
            "llama-3.1-8b-instant", {"total_tokens": 100_000}
        )
        assert cost == pytest.approx(0.005, abs=1e-8)

    def test_only_prompt_tokens_no_completion(self):
        # Should handle missing completion_tokens gracefully
        cost = calculate_cost("gpt-4o-mini", {"prompt_tokens": 5000})
        # 5000 tokens * $0.60/1M = $0.003
        assert cost == pytest.approx(0.003, abs=1e-8)

    def test_only_completion_tokens_no_prompt(self):
        cost = calculate_cost("gpt-4o-mini", {"completion_tokens": 2000})
        # 2000 tokens * $0.60/1M = $0.0012
        assert cost == pytest.approx(0.0012, abs=1e-8)

    def test_zero_total_with_nonzero_components_uses_components(self):
        # total_tokens=0 should fall through to prompt+completion sum
        cost = calculate_cost(
            "gpt-4o-mini",
            {"total_tokens": 0, "prompt_tokens": 500, "completion_tokens": 500},
        )
        assert cost == pytest.approx(0.0006, abs=1e-8)


# ---------------------------------------------------------------------------
# MODEL_REGISTRY — structural integrity
# ---------------------------------------------------------------------------


class TestModelRegistryStructure:
    def test_every_model_has_required_fields(self):
        required_fields = {"provider", "capabilities", "cost_per_1m_tokens", "context_window", "speed", "description"}
        for model_name, info in MODEL_REGISTRY.items():
            missing = required_fields - set(info.keys())
            assert missing == set(), f"{model_name} missing fields: {missing}"

    def test_capabilities_are_lists(self):
        for model_name, info in MODEL_REGISTRY.items():
            assert isinstance(info["capabilities"], list), f"{model_name} capabilities not a list"

    def test_cost_is_non_negative(self):
        for model_name, info in MODEL_REGISTRY.items():
            assert info["cost_per_1m_tokens"] >= 0, f"{model_name} has negative cost"

    def test_context_window_is_positive(self):
        for model_name, info in MODEL_REGISTRY.items():
            assert info["context_window"] > 0, f"{model_name} has non-positive context window"

    def test_speed_is_valid_tier(self):
        valid_speeds = {"ultra_fast", "very_fast", "fast", "medium"}
        for model_name, info in MODEL_REGISTRY.items():
            assert info["speed"] in valid_speeds, f"{model_name} has invalid speed: {info['speed']}"

    def test_all_providers_are_known(self):
        known_providers = {"openai", "google", "anthropic", "groq", "perplexity", "openrouter"}
        for model_name, info in MODEL_REGISTRY.items():
            assert info["provider"] in known_providers, f"{model_name} has unknown provider: {info['provider']}"

    def test_alias_points_to_existing_model(self):
        for model_name, info in MODEL_REGISTRY.items():
            if "alias_for" in info:
                target = info["alias_for"]
                assert target in MODEL_REGISTRY, f"{model_name} aliases to nonexistent {target}"
                # Target should not itself be an alias (no chains)
                assert "alias_for" not in MODEL_REGISTRY[target], f"Alias chain: {model_name} -> {target}"

    def test_registry_has_minimum_model_count(self):
        # Sanity check — registry shouldn't be accidentally emptied
        assert len(MODEL_REGISTRY) >= 10
