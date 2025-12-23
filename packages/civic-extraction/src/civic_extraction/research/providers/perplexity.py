"""
Perplexity API search provider.

Uses Perplexity's Sonar models for web search with citations.
"""

import os
from typing import Optional

import requests

from .base import SearchProvider, SearchProviderError, SearchResult


class PerplexityProvider(SearchProvider):
    """Search provider using Perplexity API."""

    DEFAULT_MODEL = "sonar-pro"
    API_URL = "https://api.perplexity.ai/chat/completions"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 90,
    ):
        """
        Initialize the Perplexity provider.

        Args:
            api_key: Perplexity API key. If None, reads from PERPLEXITY_API_KEY env var.
            model: Model to use. Defaults to sonar-pro.
            timeout: Request timeout in seconds.
        """
        self._api_key = api_key or os.environ.get("PERPLEXITY_API_KEY")
        if not self._api_key:
            raise SearchProviderError(
                provider=self.name,
                message="PERPLEXITY_API_KEY not set. "
                "Set the environment variable or pass api_key parameter.",
            )

        self._model = model or self.DEFAULT_MODEL
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "perplexity"

    def search(
        self,
        query: str,
        *,
        max_tokens: int = 4000,
        temperature: float = 0.2,
    ) -> SearchResult:
        """
        Execute a search query using Perplexity API.

        Args:
            query: The search query/prompt.
            max_tokens: Maximum tokens in response.
            temperature: Response temperature.

        Returns:
            SearchResult with content, citations, and metadata.

        Raises:
            SearchProviderError: If the API call fails.
        """
        try:
            response = requests.post(
                self.API_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": query}],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
                timeout=self._timeout,
            )

            response.raise_for_status()
            data = response.json()

            content = data["choices"][0]["message"]["content"]
            citations = data.get("citations", [])

            # Extract cost if available
            cost = 0.0
            if "usage" in data and "cost" in data["usage"]:
                cost = data["usage"]["cost"].get("total_cost", 0.0)

            return SearchResult(
                content=content,
                citations=citations,
                model=self._model,
                cost=cost,
                raw_response=data,
            )

        except requests.exceptions.Timeout as e:
            raise SearchProviderError(
                provider=self.name,
                message=f"Request timed out after {self._timeout}s",
                cause=e,
            )
        except requests.exceptions.HTTPError as e:
            raise SearchProviderError(
                provider=self.name,
                message=f"HTTP error: {e.response.status_code} - {e.response.text}",
                cause=e,
            )
        except requests.exceptions.RequestException as e:
            raise SearchProviderError(
                provider=self.name,
                message=f"Request failed: {e}",
                cause=e,
            )
        except (KeyError, IndexError) as e:
            raise SearchProviderError(
                provider=self.name,
                message=f"Unexpected response format: {e}",
                cause=e,
            )
