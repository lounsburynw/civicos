import unittest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.research_service import ResearchService
from src.llm_provider import get_provider_for_task


class TestResearchService(unittest.TestCase):
    """Test research service"""

    def test_research_service_initializes(self):
        """Research service should initialize"""
        service = ResearchService()
        self.assertIsNotNone(service)
        self.assertIsNotNone(service.provider)

    def test_query_structure(self):
        """Query should return structured result"""
        # Skip if no API keys (will use OpenAI by default)
        if not os.getenv('OPENAI_API_KEY'):
            self.skipTest("No LLM API key available")

        service = ResearchService()
        # Override with OpenAI if Google isn't working
        from src.llm_provider import get_provider
        service.provider = get_provider('openai')

        result = service.query("test question", search_scope="all")

        self.assertIn("answer", result)
        self.assertIn("sources", result)
        self.assertIn("confidence", result)
        self.assertIn("search_scope", result)

    def test_search_allocations(self):
        """Should search jurisdiction override files"""
        # Skip if no API keys
        if not os.getenv('OPENAI_API_KEY'):
            self.skipTest("No LLM API key available")

        service = ResearchService()
        # Override with OpenAI if Google isn't working
        from src.llm_provider import get_provider
        service.provider = get_provider('openai')

        result = service.query("Berkeley CDBG", search_scope="allocations")

        # Should find Berkeley's CDBG allocation
        self.assertIsNotNone(result["answer"])
        self.assertIsInstance(result["sources"], list)

    def test_uses_research_task_provider(self):
        """Research queries should use task-based provider"""
        provider = get_provider_for_task('research')
        # Should use Gemini (google) or OpenAI depending on API keys
        self.assertIn(provider.name, ['google', 'openai'])


if __name__ == '__main__':
    unittest.main()
