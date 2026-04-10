"""Tests for Perplexity search provider — init, search, error handling, cost extraction."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from civicos_extraction.research.providers.base import SearchProviderError, SearchResult
from civicos_extraction.research.providers.perplexity import PerplexityProvider


# ==================== Fixtures ====================


@pytest.fixture
def api_response_full():
    """Complete Perplexity API response with usage/cost."""
    return {
        "choices": [
            {
                "message": {
                    "content": "San Rafael's housing element was adopted in January 2023."
                }
            }
        ],
        "citations": [
            "https://www.cityofsanrafael.org/housing-element/",
            "https://abag.ca.gov/our-work/housing",
        ],
        "usage": {
            "cost": {
                "total_cost": 0.0035,
            }
        },
    }


@pytest.fixture
def api_response_no_citations():
    """API response without citations field."""
    return {
        "choices": [{"message": {"content": "The answer is 42."}}],
    }


@pytest.fixture
def api_response_no_cost():
    """API response with usage but no cost sub-key."""
    return {
        "choices": [{"message": {"content": "Result here."}}],
        "citations": ["https://example.com"],
        "usage": {"prompt_tokens": 10, "completion_tokens": 50},
    }


@pytest.fixture
def provider():
    """PerplexityProvider with a test API key."""
    return PerplexityProvider(api_key="test-key-12345")


# ==================== __init__ ====================


class TestInit:
    def test_api_key_from_parameter(self):
        p = PerplexityProvider(api_key="my-key")
        assert p._api_key == "my-key"

    @patch.dict("os.environ", {"PERPLEXITY_API_KEY": "env-key-abc"})
    def test_api_key_from_env_when_param_is_none(self):
        p = PerplexityProvider()
        assert p._api_key == "env-key-abc"

    @patch.dict("os.environ", {"PERPLEXITY_API_KEY": "env-key"})
    def test_explicit_key_overrides_env(self):
        p = PerplexityProvider(api_key="explicit-key")
        assert p._api_key == "explicit-key"

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_api_key_raises_error(self):
        # Remove PERPLEXITY_API_KEY if it exists in the patched env
        with pytest.raises(SearchProviderError, match="PERPLEXITY_API_KEY not set"):
            PerplexityProvider()

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_key_error_has_provider_name(self):
        with pytest.raises(SearchProviderError) as exc_info:
            PerplexityProvider()
        assert exc_info.value.provider == "perplexity"

    def test_default_model_is_sonar_pro(self):
        p = PerplexityProvider(api_key="k")
        assert p._model == "sonar-pro"

    def test_custom_model(self):
        p = PerplexityProvider(api_key="k", model="sonar")
        assert p._model == "sonar"

    def test_default_timeout_is_90(self):
        p = PerplexityProvider(api_key="k")
        assert p._timeout == 90

    def test_custom_timeout(self):
        p = PerplexityProvider(api_key="k", timeout=30)
        assert p._timeout == 30

    @patch.dict("os.environ", {"PERPLEXITY_API_KEY": ""})
    def test_empty_string_env_key_raises_error(self):
        with pytest.raises(SearchProviderError, match="PERPLEXITY_API_KEY not set"):
            PerplexityProvider()


# ==================== name property ====================


class TestName:
    def test_name_returns_perplexity(self, provider):
        assert provider.name == "perplexity"


# ==================== search — success paths ====================


class TestSearchSuccess:
    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_returns_content_from_api_response(self, mock_post, provider, api_response_full):
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response_full
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = provider.search("What is San Rafael's housing element?")

        assert result.content == "San Rafael's housing element was adopted in January 2023."

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_returns_citations(self, mock_post, provider, api_response_full):
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response_full
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = provider.search("housing element")

        assert result.citations == [
            "https://www.cityofsanrafael.org/housing-element/",
            "https://abag.ca.gov/our-work/housing",
        ]

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_returns_model_name(self, mock_post, provider, api_response_full):
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response_full
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = provider.search("test")

        assert result.model == "sonar-pro"

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_custom_model_reflected_in_result(self, mock_post, api_response_full):
        p = PerplexityProvider(api_key="k", model="sonar")
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response_full
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = p.search("test")

        assert result.model == "sonar"

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_extracts_cost_from_usage(self, mock_post, provider, api_response_full):
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response_full
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = provider.search("test")

        assert result.cost == 0.0035

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_raw_response_is_full_api_data(self, mock_post, provider, api_response_full):
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response_full
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = provider.search("test")

        assert result.raw_response == api_response_full
        assert result.raw_response["choices"][0]["message"]["content"] == "San Rafael's housing element was adopted in January 2023."

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_result_is_search_result_instance(self, mock_post, provider, api_response_full):
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response_full
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = provider.search("test")

        assert isinstance(result, SearchResult)
        # Also verify specific fields to avoid existence-only
        assert result.content == "San Rafael's housing element was adopted in January 2023."
        assert result.cost == 0.0035

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_missing_citations_defaults_to_empty_list(self, mock_post, provider, api_response_no_citations):
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response_no_citations
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = provider.search("test")

        assert result.citations == []

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_missing_usage_defaults_cost_to_zero(self, mock_post, provider, api_response_no_citations):
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response_no_citations
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = provider.search("test")

        assert result.cost == 0.0

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_usage_without_cost_key_defaults_to_zero(self, mock_post, provider, api_response_no_cost):
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response_no_cost
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = provider.search("test")

        assert result.cost == 0.0


# ==================== search — request construction ====================


class TestSearchRequestConstruction:
    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_posts_to_correct_url(self, mock_post, provider, api_response_full):
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response_full
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        provider.search("test query")

        assert mock_post.call_args[0][0] == "https://api.perplexity.ai/chat/completions"

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_sends_bearer_auth_header(self, mock_post, provider, api_response_full):
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response_full
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        provider.search("test")

        headers = mock_post.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer test-key-12345"

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_sends_json_content_type(self, mock_post, provider, api_response_full):
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response_full
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        provider.search("test")

        headers = mock_post.call_args[1]["headers"]
        assert headers["Content-Type"] == "application/json"

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_sends_query_as_user_message(self, mock_post, provider, api_response_full):
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response_full
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        provider.search("What is the city budget?")

        payload = mock_post.call_args[1]["json"]
        assert payload["messages"] == [{"role": "user", "content": "What is the city budget?"}]

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_sends_model_in_payload(self, mock_post, provider, api_response_full):
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response_full
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        provider.search("test")

        payload = mock_post.call_args[1]["json"]
        assert payload["model"] == "sonar-pro"

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_default_max_tokens_and_temperature(self, mock_post, provider, api_response_full):
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response_full
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        provider.search("test")

        payload = mock_post.call_args[1]["json"]
        assert payload["max_tokens"] == 4000
        assert payload["temperature"] == 0.2

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_custom_max_tokens_and_temperature(self, mock_post, provider, api_response_full):
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response_full
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        provider.search("test", max_tokens=1000, temperature=0.8)

        payload = mock_post.call_args[1]["json"]
        assert payload["max_tokens"] == 1000
        assert payload["temperature"] == 0.8

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_timeout_passed_to_request(self, mock_post, api_response_full):
        p = PerplexityProvider(api_key="k", timeout=45)
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response_full
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        p.search("test")

        assert mock_post.call_args[1]["timeout"] == 45


# ==================== search — error handling ====================


class TestSearchErrors:
    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_timeout_raises_provider_error(self, mock_post, provider):
        mock_post.side_effect = requests.exceptions.Timeout("Connection timed out")

        with pytest.raises(SearchProviderError, match="timed out after 90s"):
            provider.search("test")

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_timeout_error_has_provider_name(self, mock_post, provider):
        mock_post.side_effect = requests.exceptions.Timeout("timeout")

        with pytest.raises(SearchProviderError) as exc_info:
            provider.search("test")
        assert exc_info.value.provider == "perplexity"

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_timeout_error_preserves_cause(self, mock_post, provider):
        original = requests.exceptions.Timeout("original timeout")
        mock_post.side_effect = original

        with pytest.raises(SearchProviderError) as exc_info:
            provider.search("test")
        assert exc_info.value.cause is original

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_http_error_raises_provider_error(self, mock_post, provider):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = "Rate limit exceeded"
        http_error = requests.exceptions.HTTPError(response=mock_resp)
        mock_resp.raise_for_status.side_effect = http_error
        mock_post.return_value = mock_resp

        with pytest.raises(SearchProviderError, match="429"):
            provider.search("test")

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_http_error_includes_response_text(self, mock_post, provider):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Invalid API key"
        http_error = requests.exceptions.HTTPError(response=mock_resp)
        mock_resp.raise_for_status.side_effect = http_error
        mock_post.return_value = mock_resp

        with pytest.raises(SearchProviderError, match="Invalid API key"):
            provider.search("test")

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_connection_error_raises_provider_error(self, mock_post, provider):
        mock_post.side_effect = requests.exceptions.ConnectionError("DNS resolution failed")

        with pytest.raises(SearchProviderError, match="Request failed"):
            provider.search("test")

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_connection_error_preserves_cause(self, mock_post, provider):
        original = requests.exceptions.ConnectionError("network down")
        mock_post.side_effect = original

        with pytest.raises(SearchProviderError) as exc_info:
            provider.search("test")
        assert exc_info.value.cause is original

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_malformed_response_missing_choices_raises_error(self, mock_post, provider):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"no_choices": True}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        with pytest.raises(SearchProviderError, match="Unexpected response format"):
            provider.search("test")

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_empty_choices_array_raises_error(self, mock_post, provider):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"choices": []}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        with pytest.raises(SearchProviderError, match="Unexpected response format"):
            provider.search("test")

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_missing_message_key_raises_error(self, mock_post, provider):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"choices": [{"no_message": True}]}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        with pytest.raises(SearchProviderError, match="Unexpected response format"):
            provider.search("test")

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_missing_content_key_raises_error(self, mock_post, provider):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"choices": [{"message": {}}]}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        with pytest.raises(SearchProviderError, match="Unexpected response format"):
            provider.search("test")

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_error_provider_name_is_perplexity(self, mock_post, provider):
        mock_post.side_effect = requests.exceptions.ConnectionError("fail")

        with pytest.raises(SearchProviderError) as exc_info:
            provider.search("test")
        assert exc_info.value.provider == "perplexity"


# ==================== search — cost extraction edge cases ====================


class TestCostExtraction:
    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_usage_with_cost_but_no_total_cost_defaults_to_zero(self, mock_post, provider):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "answer"}}],
            "usage": {"cost": {"input_cost": 0.001}},
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = provider.search("test")

        assert result.cost == 0.0

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_nonzero_cost_extracted_precisely(self, mock_post, provider):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "answer"}}],
            "usage": {"cost": {"total_cost": 0.12345}},
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = provider.search("test")

        assert result.cost == 0.12345


# ==================== class-level constants ====================


class TestClassConstants:
    def test_default_model_constant(self):
        assert PerplexityProvider.DEFAULT_MODEL == "sonar-pro"

    def test_api_url_constant(self):
        assert PerplexityProvider.API_URL == "https://api.perplexity.ai/chat/completions"


# ==================== custom timeout in error message ====================


class TestTimeoutMessage:
    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_timeout_message_includes_configured_seconds(self, mock_post):
        p = PerplexityProvider(api_key="k", timeout=30)
        mock_post.side_effect = requests.exceptions.Timeout("timeout")

        with pytest.raises(SearchProviderError, match="timed out after 30s"):
            p.search("test")

    @patch("civicos_extraction.research.providers.perplexity.requests.post")
    def test_default_timeout_message_says_90s(self, mock_post):
        p = PerplexityProvider(api_key="k")
        mock_post.side_effect = requests.exceptions.Timeout("timeout")

        with pytest.raises(SearchProviderError, match="timed out after 90s"):
            p.search("test")
