import os
import sys
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from storage import Storage
from user_agent import ConversationalAgent, web_search, perform_web_search

class TestWebSearchTool(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.storage = Storage()
        await self.storage.init_db()
        self.ai_engine = AsyncMock()
        self.ai_engine.client = MagicMock()
        self.agent = ConversationalAgent(ai_engine=self.ai_engine, storage=self.storage)

    async def test_perform_web_search_success(self):
        mock_ddgs_results = [
            {"title": "Python 3.12 Release Notes", "href": "https://python.org/3.12", "body": "Python 3.12 features and updates."},
            {"title": "What's new in Python 3.12", "href": "https://docs.python.org", "body": "Summary of new features."}
        ]

        def mock_text(query, max_results=5):
            return mock_ddgs_results

        with patch("duckduckgo_search.DDGS") as mock_ddgs_cls:
            mock_instance = MagicMock()
            mock_instance.__enter__.return_value = mock_instance
            mock_instance.text = mock_text
            mock_ddgs_cls.return_value = mock_instance

            result_text = await perform_web_search("Python 3.12 news", max_results=2)
            self.assertIn("Python 3.12 Release Notes", result_text)
            self.assertIn("https://python.org/3.12", result_text)

    async def test_perform_web_search_empty(self):
        with patch("duckduckgo_search.DDGS") as mock_ddgs_cls:
            mock_instance = MagicMock()
            mock_instance.__enter__.return_value = mock_instance
            mock_instance.text.return_value = []
            mock_ddgs_cls.return_value = mock_instance

            result_text = await perform_web_search("UnfindableQueryXYZ123")
            self.assertIn("ничего не найдено", result_text)

    async def test_perform_web_search_exception_handled(self):
        with patch("duckduckgo_search.DDGS") as mock_ddgs_cls:
            mock_instance = MagicMock()
            mock_instance.__enter__.return_value = mock_instance
            mock_instance.text.side_effect = Exception("Connection Timeout")
            mock_ddgs_cls.return_value = mock_instance

            result_text = await perform_web_search("Python news")
            self.assertIn("Не удалось выполнить поиск", result_text)

    def test_tool_registration(self):
        tools = self.agent._get_tools()
        tool_names = [t.__name__ for t in tools]
        self.assertIn("web_search", tool_names)

    async def test_conversational_agent_web_search_function_call(self):
        # 1. First Gemini response calls web_search tool
        first_resp = MagicMock()
        fc = MagicMock()
        fc.name = "web_search"
        fc.args = {"query": "Курс доллара на сегодня"}
        first_resp.function_calls = [fc]

        # 2. Second Gemini response synthesizes final answer
        second_resp = MagicMock()
        second_resp.function_calls = None
        second_resp.text = "Курс доллара на сегодня составляет 90 рублей."

        self.ai_engine.generate_content_with_retry.side_effect = [first_resp, second_resp]

        mock_search_res = [
            {"title": "Курс валют", "href": "https://cbr.ru", "body": "Курс доллара 90 руб."}
        ]
        with patch("duckduckgo_search.DDGS") as mock_ddgs_cls:
            mock_instance = MagicMock()
            mock_instance.__enter__.return_value = mock_instance
            mock_instance.text.return_value = mock_search_res
            mock_ddgs_cls.return_value = mock_instance

            result = await self.agent.process_message("Найди курс доллара")
            self.assertEqual(result["text"], "Курс доллара на сегодня составляет 90 рублей.")
            self.assertIsNone(result["pending_action"])

if __name__ == "__main__":
    unittest.main()
